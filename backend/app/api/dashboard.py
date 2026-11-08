"""GET /api/dashboard: signals, quotes, tape, freshness (SRS 7.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_config, get_session, get_settings
from app.api.schemas import DashboardOut, FreshnessOut, QuoteOut, SignalOut
from app.api.serializers import txn_out
from app.config import RuntimeConfig, Settings
from app.db.models import InsiderTxn, Quote, Ticker
from app.services.freshness import build_freshness
from app.services.ingest import signals_for
from app.services.signals import shift_months

router = APIRouter()

TAPE_LIMIT = 400


@router.get("/api/dashboard", response_model=DashboardOut)
async def dashboard(
    exclude10b5_1: bool = Query(
        False, description="Exclude Rule 10b5-1 sales from signal net values"
    ),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    config: RuntimeConfig = Depends(get_config),
) -> DashboardOut:
    tickers = list(
        await session.scalars(
            select(Ticker).where(Ticker.active).order_by(Ticker.sort_order, Ticker.symbol)
        )
    )
    symbols = [ticker.symbol for ticker in tickers]
    today = date.today()

    quotes = {
        quote.symbol: QuoteOut(
            price=float(quote.price),
            changePct=float(quote.change_pct or 0),
            asOf=_iso(quote.as_of),
            source=quote.source,
            delayed=quote.delayed,
        )
        for quote in await session.scalars(select(Quote).where(Quote.symbol.in_(symbols)))
    }

    tape_rows = list(
        await session.scalars(
            select(InsiderTxn)
            .where(InsiderTxn.symbol.in_(symbols))
            .order_by(
                InsiderTxn.txn_date.desc(),
                InsiderTxn.filing_date.desc(),
                InsiderTxn.accession_no.desc(),
                InsiderTxn.line_no.desc(),
            )
            .limit(TAPE_LIMIT)
        )
    )

    results = await signals_for(
        session,
        symbols,
        today,
        config.lookback_months,
        exclude_10b5_1=exclude10b5_1,
    )
    signals = [
        SignalOut(
            ticker=symbol,
            netValue=float(results[symbol].net_value),
            txnCount=results[symbol].txn_count,
            starredCount=results[symbol].starred_count,
            clusterBuy=results[symbol].cluster_buy,
        )
        for symbol in symbols
    ]

    latest = await session.scalar(select(func.max(InsiderTxn.filing_date)))
    freshness = await build_freshness(session, settings, config)

    return DashboardOut(
        signals=signals,
        quotes=quotes,
        tape=[txn_out(row) for row in tape_rows],
        lookbackMonths=config.lookback_months,
        latestFilingDate=latest.isoformat() if latest else None,
        generatedAt=datetime.now(UTC).isoformat(),
        freshness={name: FreshnessOut(**entry.as_dict()) for name, entry in freshness.items()},
    )


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def window_start(today: date, months: int) -> date:
    return shift_months(today, -months)
