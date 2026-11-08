"""Reconcile parsed Form 4 rows against a local EDGAR snapshot (AC-01).

Run from ``backend/``:

    uv run python scripts/reconcile_edgar.py \
      --snapshot tests/fixtures/reconciliation/edgar_snapshot.json

The snapshot contains five sampled filings per watchlist ticker (40 total).
The command exits non-zero if any shares, price, code, date or owner differs.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.db.session import Database
from app.services.reconciliation import reconcile_edgar


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    return parser


async def _run(snapshot: Path, database_url: str | None) -> int:
    settings = Settings(database_url=database_url) if database_url else Settings()
    database = Database(settings.database_url)
    await database.create_all()
    try:
        async with database.session() as session:
            result = await reconcile_edgar(session, snapshot)
    finally:
        await database.dispose()
    print(
        f"edgar reconciliation: {result.checked} checked, "
        f"{result.mismatches} mismatches ({result.provider})"
    )
    return 1 if result.mismatches else 0


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        status = asyncio.run(_run(args.snapshot, args.database_url))
    except ValueError as exc:
        parser.error(str(exc))
    raise SystemExit(status)


if __name__ == "__main__":
    main()
