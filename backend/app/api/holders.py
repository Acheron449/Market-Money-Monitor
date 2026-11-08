"""GET /api/holders/{ticker}: top institutional holders (SRS 7.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.errors import ApiError
from app.api.schemas import HolderOut
from app.db.models import Holder, Ticker

router = APIRouter()


@router.get("/api/holders/{ticker}", response_model=list[HolderOut])
async def holders(
    ticker: str,
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[HolderOut]:
    symbol = ticker.upper()
    exists = await session.scalar(select(Ticker.symbol).where(Ticker.symbol == symbol))
    if exists is None:
        raise ApiError(404, "unknown_ticker", f"{symbol} is not in the watchlist")

    rows = await session.scalars(
        select(Holder).where(Holder.symbol == symbol).order_by(Holder.rank).limit(limit)
    )
    return [
        HolderOut(
            rank=row.rank,
            institution=row.institution,
            shares=float(row.shares),
            value=float(row.value),
            qoqChangePct=float(row.qoq_change_pct) if row.qoq_change_pct is not None else None,
            reportPeriod=row.report_period.isoformat(),
        )
        for row in rows
    ]
