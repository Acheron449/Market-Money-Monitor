"""Load local SEC bulk data sets for historical backfill (ING-12).

Examples (run from ``backend/``):

    uv run python scripts/load_sec_bulk.py insider --path /data/insider_transactions.zip
    uv run python scripts/load_sec_bulk.py 13f --path /data/form_13f.zip \
        --cusip-map /data/cusip-map.csv

The command reads a ZIP archive or an extracted directory containing the SEC
tab-delimited tables. It never downloads anything.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.db.session import Database
from app.services.sec_bulk import load_13f_dataset, load_insider_dataset, read_cusip_map


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("insider", "13f"))
    parser.add_argument("--path", type=Path, required=True, help="ZIP archive or directory")
    parser.add_argument("--cusip-map", type=Path, help="Optional CUSIP,symbol CSV for Form 13F")
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    parser.add_argument("--symbols", help="Comma-separated ticker filter")
    return parser


async def _run(args: argparse.Namespace) -> None:
    settings = Settings(database_url=args.database_url) if args.database_url else Settings()
    database = Database(settings.database_url)
    await database.create_all()
    symbols = (
        [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
        if args.symbols
        else None
    )
    try:
        async with database.session() as session:
            if args.dataset == "insider":
                result = await load_insider_dataset(session, args.path, symbols=symbols)
            else:
                cusip_map = read_cusip_map(args.cusip_map) if args.cusip_map else {}
                result = await load_13f_dataset(
                    session, args.path, cusip_map=cusip_map, symbols=symbols
                )
    finally:
        await database.dispose()
    print(
        f"{result.dataset}: {result.rows} rows, {result.skipped} skipped, "
        f"symbols={','.join(result.symbols) or '-'}"
    )


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
