"""Ingest one new Form 4 into the running E2E database through the fixture path.

Used by the Playwright filing-toast test so the event is a genuine ingestion
result (parser plus ingest service), not a hand-written API stub. Run from
``backend/`` with DATABASE_URL pointing at the E2E database.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.seed_demo import FixtureInsiderProvider, generated

from app.config import Settings, load_runtime_config
from app.db.session import Database
from app.providers.registry import ProviderRegistry
from app.services.ingest import active_tickers, ingest_insiders, recompute_signals


async def main() -> None:
    settings = Settings()
    config = load_runtime_config(settings)
    database = Database(settings.database_url)
    today = date.today()
    row = generated(
        symbol="NVDA",
        accession="0001045810-26-000099",
        offset=0,
        anchor=today,
        owner="HUANG JEN HSUN",
        owner_cik="1214128",
        title="President and Chief Executive Officer",
        code="P",
        shares=1200,
        price="185.00",
    )[0]
    registry = ProviderRegistry(insiders=[FixtureInsiderProvider([row])])

    async with database.session() as session:
        tickers = await active_tickers(session)
        await ingest_insiders(
            session, registry, [ticker for ticker in tickers if ticker.symbol == "NVDA"], today
        )
        await recompute_signals(
            session,
            [ticker.symbol for ticker in tickers],
            today,
            config.lookback_months,
        )

    await database.dispose()
    print("new filing", row.accession_no, row.symbol, row.value)


if __name__ == "__main__":
    asyncio.run(main())
