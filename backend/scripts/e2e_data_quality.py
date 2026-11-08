"""Exercise ING-11/ING-12 against the running E2E fixture database.

This is called by the Playwright data-quality test after the backend has seeded
the normal demo data. It loads a local SEC 13F fixture through the real loader
and runs the cross-check with a fixture second provider that disagrees on one
NVDA transaction by 20%.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import Settings
from app.db.models import InsiderTxn, Ticker
from app.db.session import Database
from app.providers.base import InsiderTxnData
from app.services.cross_check import cross_check_insiders
from app.services.sec_bulk import load_13f_dataset, read_cusip_map

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sec"


class SecondaryProvider:
    name = "fixture_secondary"

    def __init__(self, rows: list[InsiderTxnData]) -> None:
        self._rows = rows

    async def fetch_transactions(
        self, symbol: str, cik: str | None, since: date
    ) -> list[InsiderTxnData]:
        return [row for row in self._rows if row.symbol == symbol]


async def main() -> None:
    database = Database(Settings().database_url)
    await database.create_all()
    try:
        async with database.session() as session:
            cusip_map = read_cusip_map(FIXTURES / "cusip-map.csv")
            loaded = await load_13f_dataset(session, FIXTURES / "13f", cusip_map=cusip_map)
            tickers = list(await session.scalars(select(Ticker).order_by(Ticker.sort_order)))
            primary = await session.scalar(
                select(InsiderTxn)
                .where(InsiderTxn.symbol == "NVDA")
                .order_by(InsiderTxn.filing_date.desc())
                .limit(1)
            )
            if primary is None:
                raise SystemExit("E2E seed has no NVDA insider transaction")
            shares = primary.shares * Decimal("1.2")
            secondary = InsiderTxnData(
                symbol=primary.symbol,
                accession_no=f"secondary-{primary.accession_no}",
                line_no=primary.line_no,
                filing_date=primary.filing_date,
                txn_date=primary.txn_date,
                insider_name=primary.insider_name,
                insider_cik=primary.insider_cik,
                officer_title=primary.officer_title,
                role=primary.role,
                txn_code=primary.txn_code,
                action=primary.action,
                shares=shares,
                price=primary.price,
                value=(shares * primary.price) if primary.price is not None else None,
                shares_after=primary.shares_after,
                is_10b5_1=primary.is_10b5_1,
                is_amendment=primary.is_amendment,
                source="fixture_secondary",
            )
            checked = await cross_check_insiders(
                session,
                SecondaryProvider([secondary]),
                since=date.today() - timedelta(days=30),
                tickers=tickers,
            )
    finally:
        await database.dispose()
    print(
        f"13f: {loaded.rows} rows; cross-check: {checked.checked} checked, "
        f"{checked.discrepancies} discrepancies"
    )


if __name__ == "__main__":
    asyncio.run(main())
