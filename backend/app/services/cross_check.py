"""ING-11: cross-check stored insider rows against a second provider."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProviderError
from app.db.models import CrossCheckDiscrepancy, InsiderTxn, Ticker
from app.providers.base import InsiderProvider, InsiderTxnData
from app.services.ingest import active_tickers, track_run

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CrossCheckResult:
    checked: int
    discrepancies: int
    provider: str


async def cross_check_insiders(
    session: AsyncSession,
    provider: InsiderProvider,
    *,
    since: date,
    tickers: Sequence[Ticker] | None = None,
) -> CrossCheckResult:
    """Compare primary stored rows with a second provider, logging >1% differences."""

    universe = list(tickers) if tickers is not None else await active_tickers(session)
    symbols = [ticker.symbol for ticker in universe]
    primary_rows = list(
        await session.scalars(
            select(InsiderTxn)
            .where(
                InsiderTxn.symbol.in_(symbols),
                InsiderTxn.txn_date >= since,
                InsiderTxn.source != provider.name,
            )
            .order_by(InsiderTxn.symbol, InsiderTxn.txn_date)
        )
    )

    checked = 0
    discrepancies: list[CrossCheckDiscrepancy] = []
    now = datetime.now(UTC)

    async with track_run(session, job="cross_check", provider=provider.name) as run:
        for ticker in universe:
            primary_for_symbol = [row for row in primary_rows if row.symbol == ticker.symbol]
            if not primary_for_symbol:
                continue
            try:
                secondary = await provider.fetch_transactions(ticker.symbol, ticker.cik, since)
            except ProviderError as exc:
                LOGGER.warning(
                    "cross-check provider failed",
                    extra={
                        "provider": provider.name,
                        "symbol": ticker.symbol,
                        "error": str(exc),
                    },
                )
                continue
            secondary_rows = [row for row in secondary if row.symbol == ticker.symbol]
            if not secondary_rows:
                continue
            index = _secondary_index(secondary_rows)
            for primary in primary_for_symbol:
                match = _match(primary, secondary_rows, index)
                if match is None:
                    continue
                checked += 1
                discrepancies.extend(
                    _compare(
                        primary,
                        match,
                        provider.name,
                        now,
                        symbol=ticker.symbol,
                        run_id=run.id,
                    )
                )

        for discrepancy in discrepancies:
            LOGGER.warning(
                "insider cross-check discrepancy",
                extra={
                    "provider": discrepancy.provider,
                    "symbol": discrepancy.symbol,
                    "accession": discrepancy.accession_no,
                    "field": discrepancy.field,
                    "difference_pct": str(discrepancy.difference_pct),
                },
            )
        session.add_all(discrepancies)
        run.rows = checked

    return CrossCheckResult(checked, len(discrepancies), provider.name)


def _secondary_index(
    rows: Sequence[InsiderTxnData],
) -> dict[tuple[date, str, str], list[InsiderTxnData]]:
    index: dict[tuple[date, str, str], list[InsiderTxnData]] = defaultdict(list)
    for row in rows:
        index[_key(row.txn_date, row.insider_cik, row.insider_name, row.txn_code)].append(row)
    return index


def _match(
    primary: InsiderTxn,
    rows: Sequence[InsiderTxnData],
    index: dict[tuple[date, str, str], list[InsiderTxnData]],
) -> InsiderTxnData | None:
    exact = next(
        (
            row
            for row in rows
            if row.accession_no == primary.accession_no and row.line_no == primary.line_no
        ),
        None,
    )
    if exact is not None:
        return exact
    candidates = index.get(
        _key(primary.txn_date, primary.insider_cik, primary.insider_name, primary.txn_code)
    )
    return candidates[0] if candidates else None


def _key(
    txn_date: date, insider_cik: str | None, insider_name: str, txn_code: str
) -> tuple[date, str, str]:
    identity = insider_cik or insider_name.strip().upper()
    return (txn_date, identity, txn_code.upper())


def _compare(
    primary: InsiderTxn,
    secondary: InsiderTxnData,
    provider: str,
    checked_at: datetime,
    *,
    symbol: str,
    run_id: int | None,
) -> list[CrossCheckDiscrepancy]:
    result: list[CrossCheckDiscrepancy] = []
    for field, left, right in (
        ("shares", primary.shares, secondary.shares),
        ("value", primary.value, secondary.value),
    ):
        difference = _difference(left, right)
        if difference <= Decimal("1"):
            continue
        result.append(
            CrossCheckDiscrepancy(
                run_id=run_id,
                checked_at=checked_at,
                symbol=symbol,
                accession_no=primary.accession_no,
                line_no=primary.line_no,
                field=field,
                primary_value=left,
                secondary_value=right,
                difference_pct=difference,
                provider=provider,
            )
        )
    return result


def _difference(primary: Decimal | None, secondary: Decimal | None) -> Decimal:
    if primary is None and secondary is None:
        return Decimal("0")
    if primary is None or secondary is None:
        return Decimal("100")
    if primary == 0:
        return Decimal("0") if secondary == 0 else Decimal("100")
    return (abs(secondary - primary) / abs(primary) * Decimal("100")).quantize(Decimal("0.0001"))
