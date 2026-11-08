"""Ingestion orchestration: fallback chains, idempotent writes, run logging (ING-04..10)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import RuntimeConfig
from app.core.errors import ProviderError
from app.db.models import Holder, IngestRun, InsiderTxn, PriceBar, Quote, SignalSnapshot, Ticker
from app.providers.base import BarData, HolderData, InsiderTxnData, QuoteData
from app.providers.registry import ProviderRegistry
from app.providers.sec_edgar import SecEdgarClient
from app.services.signals import SignalResult, compute_signal, shift_months

LOGGER = logging.getLogger(__name__)
BACKFILL_MONTHS = 6


def utcnow() -> datetime:
    return datetime.now(UTC)


@asynccontextmanager
async def track_run(
    session: AsyncSession, *, job: str, provider: str | None = None
) -> AsyncIterator[IngestRun]:
    """Record every job run (ING-10), including failures."""

    run = IngestRun(job=job, provider=provider, started_at=utcnow(), status="running", rows=0)
    session.add(run)
    await session.commit()
    try:
        yield run
    except Exception as exc:
        await session.rollback()
        run.status = "error"
        run.error = str(exc)[:2000]
        run.finished_at = utcnow()
        session.add(run)
        await session.commit()
        raise
    else:
        run.status = "ok"
        run.finished_at = utcnow()
        session.add(run)
        await session.commit()


async def active_tickers(session: AsyncSession) -> list[Ticker]:
    rows = await session.scalars(select(Ticker).where(Ticker.active).order_by(Ticker.sort_order))
    return list(rows)


async def seed_watchlist(session: AsyncSession, config: RuntimeConfig) -> None:
    """Seed the ticker table once; afterwards the database owns the watchlist."""

    existing = await session.scalar(select(func.count()).select_from(Ticker))
    if existing:
        return
    for index, symbol in enumerate(config.watchlist):
        session.add(Ticker(symbol=symbol, active=True, sort_order=index))
    await session.commit()


async def resolve_ciks(session: AsyncSession, directory: SecEdgarClient | None) -> int:
    if directory is None:
        return 0
    mapping = await directory.company_tickers()
    updated = 0
    tickers = await session.scalars(select(Ticker))
    for ticker in tickers:
        info = mapping.get(ticker.symbol)
        if info is None:
            continue
        ticker.cik = info["cik"]
        ticker.name = info["name"] or ticker.name
        updated += 1
    await session.commit()
    return updated


async def ingest_quotes(
    session: AsyncSession, registry: ProviderRegistry, symbols: Sequence[str]
) -> int:
    if not symbols:
        return 0
    errors: list[str] = []
    for provider in registry.quotes:
        try:
            rows = await provider.fetch_quotes(list(symbols))
        except ProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
            continue
        if not rows:
            errors.append(f"{provider.name}: empty")
            continue
        async with track_run(session, job="quotes", provider=provider.name) as run:
            for row in rows:
                await _merge_quote(session, row)
            run.rows = len(rows)
        return len(rows)
    detail = "; ".join(errors) or "no providers configured"
    raise ProviderError(f"all quote providers failed: {detail}")


async def _merge_quote(session: AsyncSession, row: QuoteData) -> None:
    await session.merge(
        Quote(
            symbol=row.symbol,
            price=row.price,
            change_pct=row.change_pct,
            as_of=row.as_of,
            source=row.source,
            delayed=row.delayed,
        )
    )


async def ingest_bars(
    session: AsyncSession,
    registry: ProviderRegistry,
    symbol: str,
    start: date,
    end: date,
) -> int:
    errors: list[str] = []
    for provider in registry.bars:
        try:
            rows = await provider.fetch_bars(symbol, start, end)
        except ProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
            continue
        if not rows:
            errors.append(f"{provider.name}: empty")
            continue
        async with track_run(session, job="bars", provider=provider.name) as run:
            for row in rows:
                await _merge_bar(session, row)
            run.rows = len(rows)
        return len(rows)
    detail = "; ".join(errors) or "no providers configured"
    raise ProviderError(f"{symbol}: all bar providers failed: {detail}")


async def _merge_bar(session: AsyncSession, row: BarData) -> None:
    await session.merge(
        PriceBar(
            symbol=row.symbol,
            date=row.date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            source=row.source,
        )
    )


async def ingest_holders(session: AsyncSession, registry: ProviderRegistry, symbol: str) -> int:
    errors: list[str] = []
    for provider in registry.holders:
        try:
            rows = await provider.fetch_holders(symbol)
        except ProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
            continue
        if not rows:
            errors.append(f"{provider.name}: empty")
            continue
        async with track_run(session, job="holders", provider=provider.name) as run:
            for row in rows:
                await _merge_holder(session, row)
            run.rows = len(rows)
        return len(rows)
    detail = "; ".join(errors) or "no providers configured"
    raise ProviderError(f"{symbol}: all holder providers failed: {detail}")


async def _merge_holder(session: AsyncSession, row: HolderData) -> None:
    await session.merge(
        Holder(
            symbol=row.symbol,
            report_period=row.report_period,
            institution_cik=row.institution_cik,
            institution=row.institution,
            shares=row.shares,
            value=row.value,
            prev_shares=row.prev_shares,
            qoq_change_pct=row.qoq_change_pct,
            rank=row.rank,
            source=row.source,
        )
    )


async def ingest_insiders(
    session: AsyncSession,
    registry: ProviderRegistry,
    tickers: Sequence[Ticker],
    since: date,
) -> int:
    total = 0
    for ticker in tickers:
        symbol_since = since
        latest = await session.scalar(
            select(func.max(InsiderTxn.filing_date)).where(InsiderTxn.symbol == ticker.symbol)
        )
        if latest is not None:
            symbol_since = max(since, latest - timedelta(days=7))

        rows = await _insider_rows(session, registry, ticker, symbol_since)
        for row in rows:
            if row.is_amendment and row.insider_cik:
                await session.execute(
                    delete(InsiderTxn).where(
                        InsiderTxn.symbol == row.symbol,
                        InsiderTxn.insider_cik == row.insider_cik,
                        InsiderTxn.txn_date == row.txn_date,
                        InsiderTxn.txn_code == row.txn_code,
                        InsiderTxn.is_amendment.is_(False),
                    )
                )
            await session.merge(_txn_model(row))
        await session.commit()
        total += len(rows)
    return total


async def _insider_rows(
    session: AsyncSession,
    registry: ProviderRegistry,
    ticker: Ticker,
    since: date,
) -> list[InsiderTxnData]:
    errors: list[str] = []
    for provider in registry.insiders:
        try:
            rows = await provider.fetch_transactions(ticker.symbol, ticker.cik, since)
        except ProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
            continue
        if not rows:
            errors.append(f"{provider.name}: empty")
            continue
        async with track_run(session, job="form4", provider=provider.name) as run:
            run.rows = len(rows)
        return rows
    detail = "; ".join(errors) or "no providers configured"
    LOGGER.warning("insider ingest failed for %s: %s", ticker.symbol, detail)
    return []


def _txn_model(row: InsiderTxnData) -> InsiderTxn:
    return InsiderTxn(
        accession_no=row.accession_no,
        line_no=row.line_no,
        symbol=row.symbol,
        filing_date=row.filing_date,
        txn_date=row.txn_date,
        insider_name=row.insider_name,
        insider_cik=row.insider_cik,
        officer_title=row.officer_title,
        role=row.role,
        txn_code=row.txn_code,
        action=row.action,
        shares=row.shares,
        price=row.price,
        value=row.value,
        shares_after=row.shares_after,
        is_10b5_1=row.is_10b5_1,
        is_amendment=row.is_amendment,
        source=row.source,
    )


async def signals_for(
    session: AsyncSession, symbols: Sequence[str], as_of: date, lookback_months: int
) -> dict[str, SignalResult]:
    start = shift_months(as_of, -lookback_months)
    rows = await session.scalars(
        select(InsiderTxn).where(
            InsiderTxn.symbol.in_(list(symbols)),
            InsiderTxn.txn_date >= start,
            InsiderTxn.txn_date <= as_of,
        )
    )
    grouped: dict[str, list[InsiderTxn]] = {symbol: [] for symbol in symbols}
    for row in rows:
        grouped.setdefault(row.symbol, []).append(row)
    return {
        symbol: compute_signal(items, as_of=as_of, lookback_months=lookback_months)
        for symbol, items in grouped.items()
    }


async def recompute_signals(
    session: AsyncSession, symbols: Sequence[str], as_of: date, lookback_months: int
) -> int:
    results = await signals_for(session, symbols, as_of, lookback_months)
    await session.execute(
        delete(SignalSnapshot).where(SignalSnapshot.lookback_months == lookback_months)
    )
    snapshot_at = utcnow()
    for symbol, result in results.items():
        session.add(
            SignalSnapshot(
                symbol=symbol,
                as_of=snapshot_at,
                lookback_months=lookback_months,
                net_value=result.net_value,
                buy_value=result.buy_value,
                sell_value=result.sell_value,
                txn_count=result.txn_count,
                starred_count=result.starred_count,
            )
        )
    await session.commit()
    return len(results)


async def bars_gap_start(session: AsyncSession, symbol: str, today: date) -> date:
    latest = await session.scalar(select(func.max(PriceBar.date)).where(PriceBar.symbol == symbol))
    backfill = shift_months(today, -BACKFILL_MONTHS)
    if latest is None:
        return backfill
    return max(backfill, latest + timedelta(days=1))


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
