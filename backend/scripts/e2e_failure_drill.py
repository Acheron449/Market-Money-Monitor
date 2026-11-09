"""Inject quote-provider failures against the E2E database (AC-03, AC-04).

Run from ``backend/`` with DATABASE_URL pointing at the seeded database:

    uv run python scripts/e2e_failure_drill.py --mode fallback
    uv run python scripts/e2e_failure_drill.py --mode outage

``fallback`` disables the primary provider through the same configuration the
registry applies and runs one real quote ingest cycle, so the stored rows carry
the fallback's ``source``. ``outage`` fails every provider, proves the last-good
quotes survive, and ages them past the freshness window so the API reports them
stale. No network provider is touched.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, load_runtime_config
from app.core.errors import ProviderError
from app.db.models import IngestRun, Quote
from app.db.session import Database
from app.providers.base import QuoteData
from app.providers.registry import ProviderRegistry
from app.services.freshness import build_freshness
from app.services.ingest import active_tickers, ingest_quotes

PRIMARY_SOURCE = "alpaca"
FALLBACK_SOURCE = "finnhub"
FALLBACK_QUOTES: dict[str, tuple[str, str]] = {"NVDA": ("199.99", "3.33")}
DEFAULT_QUOTE = ("100.00", "1.00")
STALE_AFTER = timedelta(hours=1)


class ScriptedQuoteProvider:
    """Deterministic local provider: the fault-injection stand-in for a network feed."""

    def __init__(self, name: str, quotes: dict[str, tuple[str, str]]) -> None:
        self.name = name
        self._quotes = quotes

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]:
        moment = datetime.now(UTC)
        return [
            QuoteData(
                symbol=symbol,
                price=Decimal(self._quotes[symbol][0]),
                change_pct=Decimal(self._quotes[symbol][1]),
                as_of=moment,
                source=self.name,
                delayed=True,
            )
            for symbol in symbols
            if symbol in self._quotes
        ]


class FailingQuoteProvider:
    """Injected outage: every call raises the provider error the chain handles."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]:
        raise ProviderError(f"{self.name}: injected outage")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fallback", "outage"), required=True)
    return parser


async def _active_symbols(database: Database) -> list[str]:
    async with database.session() as session:
        return [ticker.symbol for ticker in await active_tickers(session)]


async def _run_fallback(database: Database, symbols: list[str]) -> None:
    quotes = {symbol: FALLBACK_QUOTES.get(symbol, DEFAULT_QUOTE) for symbol in symbols}
    registry = ProviderRegistry(
        quotes=[
            ScriptedQuoteProvider(
                PRIMARY_SOURCE, {symbol: ("150.00", "-1.00") for symbol in symbols}
            ),
            ScriptedQuoteProvider(FALLBACK_SOURCE, quotes),
        ]
    )
    registry.disable([PRIMARY_SOURCE])
    if [provider.name for provider in registry.quotes] != [FALLBACK_SOURCE]:
        raise SystemExit(f"fallback drill failed: chain is {[p.name for p in registry.quotes]}")

    async with database.session() as session:
        written = await ingest_quotes(session, registry, symbols)
        stored = {row.symbol: row.source for row in await session.scalars(select(Quote))}
        run = await session.scalar(
            select(IngestRun).where(IngestRun.job == "quotes").order_by(IngestRun.id.desc())
        )

    if written != len(symbols):
        raise SystemExit(f"fallback drill failed: wrote {written} of {len(symbols)} quotes")
    sources = {stored.get(symbol) for symbol in symbols}
    if sources != {FALLBACK_SOURCE}:
        raise SystemExit(f"fallback drill failed: sources are {sorted(sources)}")
    if run is None or run.provider != FALLBACK_SOURCE or run.status != "ok":
        raise SystemExit("fallback drill failed: the ingest run did not record the fallback")
    print(f"fallback: {FALLBACK_SOURCE} served {written} quotes ({PRIMARY_SOURCE} disabled)")


async def _run_outage(database: Database, symbols: list[str]) -> None:
    async with database.session() as session:
        before = {
            row.symbol: row.price
            for row in await session.scalars(select(Quote))
            if row.symbol in symbols
        }
        await session.execute(update(Quote).values(as_of=datetime.now(UTC) - STALE_AFTER))
        await session.commit()

    registry = ProviderRegistry(
        quotes=[FailingQuoteProvider(PRIMARY_SOURCE), FailingQuoteProvider(FALLBACK_SOURCE)]
    )
    async with database.session() as session:
        try:
            await ingest_quotes(session, registry, symbols)
        except ProviderError:
            pass
        else:
            raise SystemExit("outage drill failed: the ingest unexpectedly succeeded")
        after = {
            row.symbol: row.price
            for row in await session.scalars(select(Quote))
            if row.symbol in symbols
        }
        freshness = await build_freshness(session, Settings(), load_runtime_config(Settings()))

    if after != before:
        raise SystemExit("outage drill failed: last-good quotes changed during the outage")
    if not freshness["quotes"].stale:
        raise SystemExit("outage drill failed: the API did not report quotes as stale")
    print(
        f"outage: last-good kept for {len(after)} quotes, "
        f"quotes stale after {int(STALE_AFTER.total_seconds())} s"
    )


async def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    database = Database(Settings().database_url)
    await database.create_all()
    try:
        symbols = await _active_symbols(database)
        if not symbols:
            raise SystemExit("failure drill needs a seeded watchlist")
        if args.mode == "fallback":
            await _run_fallback(database, symbols)
        else:
            await _run_outage(database, symbols)
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
