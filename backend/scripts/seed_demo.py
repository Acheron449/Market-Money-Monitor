"""Seed a deterministic demo database through the real parse/ingest path.

Run from ``backend/``:

    DATABASE_URL=sqlite+aiosqlite:///./e2e.db uv run python scripts/seed_demo.py

The SEC fixtures are parsed by ``app.parsers.form4`` and written by
``app.services.ingest`` (the same upsert and run-logging code the jobs use), so the
UI is exercised on data that travelled the production path rather than hand-inserted
rows. No network provider is touched.
"""

from __future__ import annotations

import asyncio
import math
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import Settings, load_runtime_config
from app.db.models import Ticker
from app.db.session import Database
from app.parsers.form4 import parse_form4
from app.providers.base import BarData, HolderData, InsiderTxnData, QuoteData
from app.providers.registry import ProviderRegistry
from app.services.ingest import (
    ingest_bars,
    ingest_holders,
    ingest_insiders,
    ingest_quotes,
    recompute_signals,
    seed_watchlist,
)
from app.services.signals import shift_months

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "form4"

COMPANIES: dict[str, tuple[str, str]] = {
    "NVDA": ("0001045810", "NVIDIA CORP"),
    "AAPL": ("0000320193", "Apple Inc."),
    "TSLA": ("0001318605", "Tesla, Inc."),
    "AMZN": ("0001018724", "Amazon.com, Inc."),
    "META": ("0001326801", "Meta Platforms, Inc."),
    "AMD": ("0000002488", "Advanced Micro Devices, Inc."),
    "PLTR": ("0001321655", "Palantir Technologies Inc."),
    "COIN": ("0001679788", "Coinbase Global, Inc."),
    "MSFT": ("0000789019", "Microsoft Corp"),
}

# Resolved but not on the initial watchlist: the editor can activate these and their
# seeded quotes, bars, holders and filings immediately appear on the dashboard.
OFF_WATCHLIST = ("MSFT",)

QUOTES: dict[str, tuple[str, str]] = {
    "NVDA": ("182.50", "1.25"),
    "AAPL": ("271.14", "-0.42"),
    "TSLA": ("240.00", "-2.10"),
    "AMZN": ("210.00", "0.88"),
    "META": ("612.30", "3.40"),
    "AMD": ("245.61", "-1.15"),
    "PLTR": ("35.00", "2.05"),
    "COIN": ("310.20", "-0.65"),
    "MSFT": ("415.20", "0.65"),
}

HOLDERS = [
    ("VANGUARD GROUP INC", "0000102909", 92_000_000, 4.2),
    ("BLACKROCK, INC.", "0001364742", 78_500_000, 1.8),
    ("STATE STREET CORP", "0000093751", 41_200_000, None),
    ("FMR LLC", "0000315066", 33_900_000, -3.1),
    ("GEODE CAPITAL MANAGEMENT", "0001214717", 18_400_000, 0.6),
]

XML_TEMPLATE = """<?xml version="1.0"?>
<ownershipDocument>
  <schemaVersion>X0608</schemaVersion>
  <documentType>{document_type}</documentType>
  <periodOfReport>{txn_date}</periodOfReport>
  <issuer>
    <issuerCik>{cik}</issuerCik>
    <issuerName>{company}</issuerName>
    <issuerTradingSymbol>{symbol}</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>{owner_cik}</rptOwnerCik>
      <rptOwnerName>{owner}</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>{is_director}</isDirector>
      <isOfficer>{is_officer}</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>{title}</officerTitle>
      <aff10b5One>{plan}</aff10b5One>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>{txn_date}</value></transactionDate>
      <transactionCoding>
        <transactionFormType>4</transactionFormType>
        <transactionCode>{code}</transactionCode>
        <equitySwapInvolved>0</equitySwapInvolved>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>{after}</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature>
        <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
      </ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


class FixtureInsiderProvider:
    name = "fixtures"

    def __init__(self, rows: list[InsiderTxnData]) -> None:
        self._rows = rows

    async def fetch_transactions(
        self, symbol: str, cik: str | None, since: date
    ) -> list[InsiderTxnData]:
        return [row for row in self._rows if row.symbol == symbol]


class FixtureQuoteProvider:
    name = "fixtures"

    def __init__(self, quotes: list[QuoteData]) -> None:
        self._quotes = quotes

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]:
        return [quote for quote in self._quotes if quote.symbol in symbols]


class FixtureBarProvider:
    name = "fixtures"

    def __init__(self, bars: dict[str, list[BarData]]) -> None:
        self._bars = bars

    async def fetch_bars(self, symbol: str, start: date, end: date) -> list[BarData]:
        return [bar for bar in self._bars.get(symbol, []) if start <= bar.date <= end]


class FixtureHolderProvider:
    name = "fixtures"

    def __init__(self, holders: dict[str, list[HolderData]]) -> None:
        self._holders = holders

    async def fetch_holders(self, symbol: str) -> list[HolderData]:
        return self._holders.get(symbol, [])


def previous_weekday(day: date) -> date:
    """Keep seeded trades on NYSE sessions so they land inside the bar series."""

    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def shift(
    rows: list[InsiderTxnData], symbol: str, offset: int, anchor: date
) -> list[InsiderTxnData]:
    """Anchor fixture dates to the demo day so the lookback window always covers them."""

    txn_date = previous_weekday(anchor - timedelta(days=offset))
    filing_date = min(anchor, txn_date + timedelta(days=1))
    return [replace(row, symbol=symbol, txn_date=txn_date, filing_date=filing_date) for row in rows]


def from_fixture(
    filename: str, symbol: str, accession: str, offset: int, anchor: date
) -> list[InsiderTxnData]:
    parsed = parse_form4(
        (FIXTURES / filename).read_bytes(),
        accession_no=accession,
        filing_date=anchor,
        fallback_symbol=symbol,
    )
    return shift(parsed.transactions, symbol, offset, anchor)


def generated(
    *,
    symbol: str,
    accession: str,
    offset: int,
    anchor: date,
    owner: str,
    owner_cik: str,
    title: str,
    code: str,
    shares: int,
    price: str,
    plan: int = 0,
    document_type: str = "4",
    is_director: int = 0,
    is_officer: int = 1,
) -> list[InsiderTxnData]:
    cik, company = COMPANIES[symbol]
    txn_date = previous_weekday(anchor - timedelta(days=offset))
    xml = XML_TEMPLATE.format(
        document_type=document_type,
        txn_date=txn_date.isoformat(),
        cik=cik,
        company=company,
        symbol=symbol,
        owner_cik=owner_cik,
        owner=owner,
        is_director=is_director,
        is_officer=is_officer,
        title=title,
        plan=plan,
        code=code,
        shares=shares,
        price=price,
        ad="A" if code in {"P", "A", "M"} else "D",
        after=50_000_000,
    )
    parsed = parse_form4(
        xml,
        accession_no=accession,
        filing_date=min(anchor, txn_date + timedelta(days=1)),
        fallback_symbol=symbol,
    )
    return list(parsed.transactions)


def insider_rows(anchor: date) -> list[InsiderTxnData]:
    rows: list[InsiderTxnData] = []
    # Real SEC fixtures, parsed by the production parser.
    rows += from_fixture("ceo_open_market_buy.xml", "NVDA", "0001045810-26-000001", 6, anchor)
    rows += from_fixture("cfo_10b5_sale.xml", "COIN", "0001679788-26-000002", 3, anchor)
    rows += from_fixture("joint_filers.xml", "AAPL", "0000320193-26-000003", 4, anchor)
    rows += from_fixture("award_and_gift.xml", "META", "0001326801-26-000004", 2, anchor)
    rows += from_fixture("amendment.xml", "AMD", "0000002488-26-000005", 5, anchor)

    # Additional deterministic filings so every tile has signal and every date rule is covered.
    rows += generated(
        symbol="NVDA",
        accession="0001045810-26-000006",
        offset=6,
        anchor=anchor,
        owner="STEVENS MARK A",
        owner_cik="0001214156",
        title="Director",
        code="P",
        shares=500,
        price="200.00",
        is_director=1,
        is_officer=0,
    )
    rows += generated(
        symbol="NVDA",
        accession="0001045810-26-000007",
        offset=4,
        anchor=anchor,
        owner="STEVENS MARK A",
        owner_cik="0001214156",
        title="Director",
        code="S",
        shares=3000,
        price="200.00",
        is_director=1,
        is_officer=0,
    )
    rows += generated(
        symbol="NVDA",
        accession="0001045810-26-000008",
        offset=1,
        anchor=anchor,
        owner="COLEMAN DWIGHT",
        owner_cik="0001771340",
        title="Chief Financial Officer",
        code="P",
        shares=5000,
        price="180.00",
    )
    rows += generated(
        symbol="AMZN",
        accession="0001018724-26-000009",
        offset=2,
        anchor=anchor,
        owner="OLSAVSKY BRIAN T",
        owner_cik="0001715680",
        title="Chief Financial Officer",
        code="P",
        shares=5000,
        price="210.00",
    )
    rows += generated(
        symbol="TSLA",
        accession="0001318605-26-000010",
        offset=3,
        anchor=anchor,
        owner="DENHOLM ROBYN M",
        owner_cik="0001494730",
        title="Director",
        code="P",
        shares=2000,
        price="240.00",
        is_director=1,
        is_officer=0,
    )
    rows += generated(
        symbol="PLTR",
        accession="0001321655-26-000011",
        offset=2,
        anchor=anchor,
        owner="THIEL PETER A",
        owner_cik="0001565724",
        title="Director",
        code="S",
        shares=4000,
        price="35.00",
        is_director=1,
        is_officer=0,
    )
    rows += generated(
        symbol="MSFT",
        accession="0000789019-26-000012",
        offset=2,
        anchor=anchor,
        owner="HOOD AMY E",
        owner_cik="0001745109",
        title="Chief Financial Officer",
        code="P",
        shares=800,
        price="415.00",
    )
    rows += generated(
        symbol="MSFT",
        accession="0000789019-26-000013",
        offset=4,
        anchor=anchor,
        owner="NADELLA SATYA",
        owner_cik="0001477405",
        title="Chief Executive Officer",
        code="S",
        shares=100,
        price="410.00",
    )
    return rows


def quote_rows(now: datetime) -> list[QuoteData]:
    quotes: list[QuoteData] = []
    for index, (symbol, (price, change)) in enumerate(QUOTES.items()):
        quotes.append(
            QuoteData(
                symbol=symbol,
                price=Decimal(price),
                change_pct=Decimal(change),
                as_of=now - timedelta(seconds=index * 3),
                source="fixtures",
                delayed=True,
            )
        )
    return quotes


def bar_rows(anchor: date, per_symbol: int = 130) -> dict[str, list[BarData]]:
    result: dict[str, list[BarData]] = {}
    for symbol, (price, _) in QUOTES.items():
        base = Decimal(price) * Decimal("0.88")
        days: list[date] = []
        cursor = anchor
        while len(days) < per_symbol:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor -= timedelta(days=1)
        days.reverse()

        bars = [
            BarData(
                symbol=symbol,
                date=day,
                close=(
                    base * Decimal(str(round(1 + 0.06 * math.sin(index / 9) + 0.0006 * index, 4)))
                ).quantize(Decimal("0.01")),
                source="fixtures",
                volume=1_000_000 + index * 1_000,
            )
            for index, day in enumerate(days)
        ]
        if bars:
            bars[-1] = replace(bars[-1], close=Decimal(price))
        result[symbol] = bars
    return result


def holder_rows(anchor: date) -> dict[str, list[HolderData]]:
    quarter_end = _quarter_end(anchor)
    result: dict[str, list[HolderData]] = {}
    for symbol in COMPANIES:
        rows: list[HolderData] = []
        for rank, (name, cik, shares, qoq) in enumerate(HOLDERS, start=1):
            prev = int(shares / (1 + qoq / 100)) if qoq is not None else None
            rows.append(
                HolderData(
                    symbol=symbol,
                    institution=name,
                    institution_cik=f"{symbol}-{cik}",
                    shares=Decimal(shares),
                    value=(Decimal(shares) * Decimal(QUOTES[symbol][0])).quantize(Decimal("1")),
                    report_period=quarter_end,
                    rank=rank,
                    source="fixtures",
                    prev_shares=Decimal(prev) if prev is not None else None,
                    qoq_change_pct=Decimal(str(qoq)) if qoq is not None else None,
                )
            )
        result[symbol] = rows
    return result


def _quarter_end(day: date) -> date:
    quarter_start_month = ((day.month - 1) // 3) * 3 + 1
    start = date(day.year, quarter_start_month, 1)
    return start - timedelta(days=1)


async def main() -> None:
    settings = Settings()
    config = load_runtime_config(settings)
    database = Database(settings.database_url)
    await database.create_all()

    anchor = date.today()
    now = datetime.now(UTC)
    rows = insider_rows(anchor)
    quotes = quote_rows(now)
    bars = bar_rows(anchor)
    holders = holder_rows(anchor)

    registry = ProviderRegistry(
        quotes=[FixtureQuoteProvider(quotes)],
        bars=[FixtureBarProvider(bars)],
        insiders=[FixtureInsiderProvider(rows)],
        holders=[FixtureHolderProvider(holders)],
    )

    async with database.session() as session:
        await seed_watchlist(session, config)
        tickers = list(await session.scalars(select(Ticker).order_by(Ticker.sort_order)))
        known = {ticker.symbol for ticker in tickers}
        for index, symbol in enumerate(OFF_WATCHLIST):
            if symbol not in known:
                session.add(Ticker(symbol=symbol, active=False, sort_order=100 + index))
        await session.flush()
        tickers = list(await session.scalars(select(Ticker).order_by(Ticker.sort_order)))
        for ticker in tickers:
            cik, company = COMPANIES.get(ticker.symbol, (None, ticker.symbol))
            ticker.cik = cik
            ticker.name = company
            ticker.exchange = "NASDAQ"
        await session.commit()

        await ingest_quotes(session, registry, [ticker.symbol for ticker in tickers])
        await ingest_insiders(session, registry, tickers, shift_months(anchor, -6))
        for ticker in tickers:
            await ingest_bars(session, registry, ticker.symbol, shift_months(anchor, -6), anchor)
            await ingest_holders(session, registry, ticker.symbol)
        await recompute_signals(
            session, [ticker.symbol for ticker in tickers], anchor, config.lookback_months
        )

    await database.dispose()

    signals = {row.symbol: row for row in rows}
    print(
        "seeded",
        len(signals),
        "insider symbols,",
        len(rows),
        "transactions,",
        len(quotes),
        "quotes,",
        sum(len(value) for value in bars.values()),
        "bars,",
        sum(len(value) for value in holders.values()),
        "holders",
    )


if __name__ == "__main__":
    asyncio.run(main())
