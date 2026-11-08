"""GET /api/stream: Server-Sent Events for quotes and new filings (AUT-03, AUT-07).

The stream reads the store; providers are never called in the request path. The
first frame is a snapshot of every active quote; later frames carry only quotes
whose price, change, timestamp or source changed. Insider transactions inserted
after the connection is established are published as ``filings`` frames. A
comment-line heartbeat keeps proxies from closing an idle connection.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.schemas import QuoteOut, StreamFilingsOut, StreamQuotesOut
from app.api.serializers import txn_out
from app.config import Settings
from app.db.models import InsiderTxn, Quote, Ticker
from app.db.session import Database

router = APIRouter()

RETRY_MS = 3000


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def _fingerprint(quote: QuoteOut) -> tuple[float, float, str, str, bool]:
    return (quote.price, quote.changePct, quote.asOf, quote.source, quote.delayed)


def _txn_key(row: InsiderTxn) -> str:
    return f"{row.accession_no}:{row.line_no}"


async def _active_symbols(database: Database) -> list[str]:
    async with database.session() as session:
        return list(
            await session.scalars(
                select(Ticker.symbol)
                .where(Ticker.active)
                .order_by(Ticker.sort_order, Ticker.symbol)
            )
        )


async def _active_quotes(database: Database) -> dict[str, QuoteOut]:
    symbols = await _active_symbols(database)
    if not symbols:
        return {}
    async with database.session() as session:
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


async def _filings_since(
    database: Database,
    watermark: datetime | None,
    seen: set[str],
) -> tuple[datetime | None, list[InsiderTxn]]:
    """Return filings inserted since the last poll and the new watermark.

    The first call establishes a baseline (all current keys at the newest
    timestamp are marked seen) so a fresh page load never toasts history.
    Rows are matched with ``>=`` and filtered by key, which also catches rows
    sharing a second-resolution SQLite timestamp.
    """

    symbols = await _active_symbols(database)
    if not symbols:
        return watermark, []

    async with database.session() as session:
        latest = await session.scalar(
            select(func.max(InsiderTxn.created_at)).where(InsiderTxn.symbol.in_(symbols))
        )
        if watermark is None:
            if latest is None:
                return datetime.now(UTC).replace(tzinfo=None), []
            baseline = await session.scalars(
                select(InsiderTxn).where(
                    InsiderTxn.symbol.in_(symbols),
                    InsiderTxn.created_at == latest,
                )
            )
            seen.update(_txn_key(row) for row in baseline)
            return latest, []

        rows = list(
            await session.scalars(
                select(InsiderTxn)
                .where(
                    InsiderTxn.symbol.in_(symbols),
                    InsiderTxn.created_at >= watermark,
                )
                .order_by(
                    InsiderTxn.created_at,
                    InsiderTxn.accession_no,
                    InsiderTxn.line_no,
                )
                .limit(50)
            )
        )
        fresh = [row for row in rows if _txn_key(row) not in seen]
        return latest or watermark, fresh


def _event(name: str, payload: StreamQuotesOut | StreamFilingsOut) -> str:
    data = json.dumps(payload.model_dump(), separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n"


async def _quote_events(database: Database, settings: Settings) -> AsyncIterator[str]:
    previous: dict[str, tuple[float, float, str, str, bool]] = {}
    seen: set[str] = set()
    # Baseline before the first frame so history never toasts and an insert
    # immediately after connect is still observed.
    watermark, _ = await _filings_since(database, None, seen)
    yield f"retry: {RETRY_MS}\n\n"
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

        watermark, filings = await _filings_since(database, watermark, seen)
        if filings:
            yield _event(
                "filings",
                StreamFilingsOut(
                    filings=[txn_out(row) for row in filings],
                    generatedAt=datetime.now(UTC).isoformat(),
                ),
            )
            seen.update(_txn_key(row) for row in filings)

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
