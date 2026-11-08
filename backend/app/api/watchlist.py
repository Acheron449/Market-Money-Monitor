"""GET/PUT /api/watchlist (UI-12; PUT is an ADM-02 admin endpoint)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_settings, require_admin
from app.api.errors import ApiError
from app.api.schemas import WatchlistIn, WatchlistOut
from app.config import Settings
from app.db.models import Ticker

router = APIRouter()
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


@router.get("/api/watchlist", response_model=WatchlistOut)
async def read_watchlist(session: AsyncSession = Depends(get_session)) -> WatchlistOut:
    rows = await session.scalars(
        select(Ticker).where(Ticker.active).order_by(Ticker.sort_order, Ticker.symbol)
    )
    return WatchlistOut(tickers=[row.symbol for row in rows])


@router.put("/api/watchlist", response_model=WatchlistOut)
async def replace_watchlist(
    payload: WatchlistIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WatchlistOut:
    require_admin(request, settings)

    symbols: list[str] = []
    for raw in payload.tickers:
        symbol = raw.strip().upper()
        if not SYMBOL_RE.match(symbol):
            raise ApiError(422, "invalid_ticker", f"{raw!r} is not a valid ticker")
        if symbol not in symbols:
            symbols.append(symbol)
    if not symbols:
        raise ApiError(422, "empty_watchlist", "The watchlist cannot be empty")
    if len(symbols) > 50:
        raise ApiError(422, "watchlist_too_large", "At most 50 tickers are supported")

    existing = {row.symbol: row for row in await session.scalars(select(Ticker))}
    # The editor can only activate symbols already in the resolved universe. A CIK
    # is resolved when that symbol is first added to the universe, never lazily on
    # a write, so an unknown ticker cannot silently create a data-less tile.
    unknown = [symbol for symbol in symbols if symbol not in existing]
    if unknown:
        raise ApiError(
            422,
            "unknown_ticker",
            f"{unknown[0]} is not in the known ticker universe",
        )

    for order, symbol in enumerate(symbols):
        row = existing[symbol]
        row.active = True
        row.sort_order = order
    for symbol, row in existing.items():
        if symbol not in symbols:
            row.active = False
    await session.commit()

    request.app.state.config.watchlist = symbols
    return WatchlistOut(tickers=symbols)
