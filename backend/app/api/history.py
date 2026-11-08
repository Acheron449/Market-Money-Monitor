"""GET /api/history/{ticker}: daily closes (SRS 7.1)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.errors import ApiError
from app.api.schemas import HistoryPoint
from app.db.models import PriceBar, Ticker
from app.services.signals import shift_months

router = APIRouter()


@router.get("/api/history/{ticker}", response_model=list[HistoryPoint])
async def history(
    ticker: str,
    months: int = Query(6, ge=1, le=24),
    session: AsyncSession = Depends(get_session),
) -> list[HistoryPoint]:
    symbol = ticker.upper()
    exists = await session.scalar(select(Ticker.symbol).where(Ticker.symbol == symbol))
    if exists is None:
        raise ApiError(404, "unknown_ticker", f"{symbol} is not in the watchlist")

    start = shift_months(date.today(), -months)
    rows = await session.scalars(
        select(PriceBar)
        .where(PriceBar.symbol == symbol, PriceBar.date >= start)
        .order_by(PriceBar.date)
    )
    return [HistoryPoint(date=row.date.isoformat(), close=float(row.close)) for row in rows]
