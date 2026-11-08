"""Run the AC-01 reconciliation fixture against the E2E database."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.db.session import Database
from app.services.reconciliation import reconcile_edgar

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests" / "fixtures" / "reconciliation" / "edgar_snapshot.json"


async def main() -> None:
    database = Database(Settings().database_url)
    await database.create_all()
    try:
        async with database.session() as session:
            result = await reconcile_edgar(session, SNAPSHOT)
    finally:
        await database.dispose()
    print(f"edgar reconciliation: {result.checked} checked, {result.mismatches} mismatches")


if __name__ == "__main__":
    asyncio.run(main())
