"""Contract tests for the SSE quote stream (AUT-03)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal

from starlette.requests import Request

from app.api.stream import _quote_events, stream
from app.db.models import Quote


def _data(chunk: str) -> dict[str, object]:
    line = next(line for line in chunk.splitlines() if line.startswith("data: "))
    payload: dict[str, object] = json.loads(line[6:])
    return payload


async def test_stream_snapshot_then_only_changed_quotes(seeded) -> None:  # type: ignore[no-untyped-def]
    settings = seeded.state.settings
    settings.stream_poll_seconds = 0.01
    settings.stream_heartbeat_seconds = 5
    events = _quote_events(seeded.state.db, settings)

    assert await anext(events) == "retry: 3000\n\n"
    snapshot = _data(await anext(events))
    quotes = snapshot["quotes"]
    assert isinstance(quotes, dict)
    assert set(quotes) == {"NVDA"}
    assert quotes["NVDA"]["price"] == 182.5  # type: ignore[index]
    assert quotes["NVDA"]["source"] == "alpaca"  # type: ignore[index]

    async with seeded.state.db.session() as session:
        quote = await session.get(Quote, "NVDA")
        assert quote is not None
        quote.price = Decimal("190.25")
        quote.change_pct = Decimal("2.75")
        quote.as_of = datetime.now(UTC)
        await session.commit()

    tick = _data(await anext(events))
    changed = tick["quotes"]
    assert isinstance(changed, dict)
    assert set(changed) == {"NVDA"}
    assert changed["NVDA"]["price"] == 190.25  # type: ignore[index]
    assert changed["NVDA"]["changePct"] == 2.75  # type: ignore[index]
    await events.aclose()


async def test_stream_emits_heartbeat_comments(seeded) -> None:  # type: ignore[no-untyped-def]
    settings = seeded.state.settings
    settings.stream_poll_seconds = 0.01
    settings.stream_heartbeat_seconds = 0.02
    events = _quote_events(seeded.state.db, settings)

    await anext(events)  # retry hint
    await anext(events)  # quote snapshot
    async with asyncio.timeout(2):
        while True:
            chunk = await anext(events)
            if chunk == ": heartbeat\n\n":
                break
    await events.aclose()


async def test_stream_route_sets_sse_headers(seeded) -> None:  # type: ignore[no-untyped-def]
    request = Request(
        {
            "type": "http",
            "app": seeded,
            "method": "GET",
            "path": "/api/stream",
            "headers": [],
        }
    )
    response = await stream(request)

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["connection"] == "keep-alive"

    closer = getattr(response.body_iterator, "aclose", None)
    if closer is not None:
        await closer()
