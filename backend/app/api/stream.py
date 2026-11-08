"""GET /api/stream: Server-Sent Events quote ticks with a 20 s heartbeat (AUT-03).

The stream reads the store; providers are never called in the request path. The
first frame is a snapshot of every active quote, later frames carry only quotes
whose price, change, timestamp or source changed. A comment-line heartbeat keeps
proxies from closing an idle connection.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.schemas import QuoteOut, StreamQuotesOut
from app.config import Settings
from app.db.models import Quote, Ticker
from app.db.session import Database

router = APIRouter()

RETRY_MS = 3000


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def _fingerprint(quote: QuoteOut) -> tuple[float, float, str, str, bool]:
    return (quote.price, quote.changePct, quote.asOf, quote.source, quote.delayed)


async def _active_quotes(database: Database) -> dict[str, QuoteOut]:
    async with database.session() as session:
        symbols = list(
            await session.scalars(
                select(Ticker.symbol)
                .where(Ticker.active)
                .order_by(Ticker.sort_order, Ticker.symbol)
            )
        )
        if not symbols:
            return {}
        rows = await session.scalars(select(Quote).where(Quote.symbol.in_(symbols)))
        return {
            row.symbol: QuoteOut(
                price=float(row.price),
                changePct=float(row.change_pct or 0),
                asOf=_iso(row.as_of),
                source=row.source,
                delayed=row.delayed,
            )
            for row in rows
        }


def _event(name: str, payload: StreamQuotesOut) -> str:
    data = json.dumps(payload.model_dump(), separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n"


async def _quote_events(database: Database, settings: Settings) -> AsyncIterator[str]:
    yield f"retry: {RETRY_MS}\n\n"
    previous: dict[str, tuple[float, float, str, str, bool]] = {}
    last_heartbeat = time.monotonic()

    while True:
        quotes = await _active_quotes(database)
        changed = {
            symbol: quote
            for symbol, quote in quotes.items()
            if previous.get(symbol) != _fingerprint(quote)
        }
        if changed:
            yield _event(
                "quotes",
                StreamQuotesOut(quotes=changed, generatedAt=datetime.now(UTC).isoformat()),
            )
            previous.update({symbol: _fingerprint(quote) for symbol, quote in changed.items()})

        now = time.monotonic()
        if now - last_heartbeat >= settings.stream_heartbeat_seconds:
            yield ": heartbeat\n\n"
            last_heartbeat = now
        await asyncio.sleep(settings.stream_poll_seconds)


@router.get("/api/stream")
async def stream(request: Request) -> StreamingResponse:
    database: Database = request.app.state.db
    settings: Settings = request.app.state.settings
    return StreamingResponse(
        _quote_events(database, settings),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
