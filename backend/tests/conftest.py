"""Test fixtures: an isolated SQLite database and a seeded API client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Holder, InsiderTxn, PriceBar, Quote, Ticker
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "form4"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        scheduler_enabled=False,
        admin_token="test-token",
        sec_user_agent="Smart Money Monitor tests test@example.com",
    )


@pytest_asyncio.fixture
async def app(settings: Settings):  # type: ignore[no-untyped-def]
    application = create_app(settings)
    await application.state.db.create_all()
    yield application
    for task in list(application.state.tasks):
        task.cancel()
    await application.state.registry.close()
    await application.state.db.dispose()


async def seed_market_data(session: AsyncSession) -> None:
    today = date.today()
    session.add_all(
        [
            Ticker(
                symbol="NVDA",
                cik="0001045810",
                name="NVIDIA CORP",
                exchange="NASDAQ",
                active=True,
                sort_order=0,
            ),
            Ticker(
                symbol="AAPL",
                cik="0000320193",
                name="Apple Inc.",
                exchange="NASDAQ",
                active=True,
                sort_order=1,
            ),
            Ticker(symbol="OLD", active=False, sort_order=9),
        ]
    )
    session.add_all(
        [
            Quote(
                symbol="NVDA",
                price=Decimal("182.50"),
                change_pct=Decimal("1.25"),
                as_of=datetime.now(UTC),
                source="alpaca",
                delayed=True,
            ),
            # Inactive but resolved: activating it through /api/watchlist must make
            # every read path render its seeded data.
            Quote(
                symbol="OLD",
                price=Decimal("50.00"),
                change_pct=Decimal("2.00"),
                as_of=datetime.now(UTC),
                source="fixtures",
                delayed=True,
            ),
        ]
    )
    session.add_all(
        [
            PriceBar(
                symbol="NVDA",
                date=today - timedelta(days=1),
                close=Decimal("180.00"),
                source="alpaca",
            ),
            PriceBar(
                symbol="OLD",
                date=today - timedelta(days=1),
                close=Decimal("48.00"),
                source="fixtures",
            ),
        ]
    )
    session.add_all(
        [
            InsiderTxn(
                accession_no="0001-26-000001",
                line_no=1,
                symbol="NVDA",
                filing_date=today,
                txn_date=today - timedelta(days=2),
                insider_name="HUANG JEN HSUN",
                insider_cik="1214128",
                officer_title="President and Chief Executive Officer",
                role="CEO",
                txn_code="P",
                action="buy",
                shares=Decimal("1000"),
                price=Decimal("100"),
                value=Decimal("100000"),
                shares_after=Decimal("85000000"),
                is_10b5_1=False,
                is_amendment=False,
                source="sec_edgar",
            ),
            InsiderTxn(
                accession_no="0001-26-000002",
                line_no=1,
                symbol="NVDA",
                filing_date=today,
                txn_date=today - timedelta(days=1),
                insider_name="COLEMAN DWIGHT",
                insider_cik="1771340",
                officer_title="Chief Financial Officer",
                role="CFO",
                txn_code="S",
                action="sell",
                shares=Decimal("500"),
                price=Decimal("100"),
                value=Decimal("50000"),
                shares_after=None,
                is_10b5_1=True,
                is_amendment=False,
                source="sec_edgar",
            ),
            InsiderTxn(
                accession_no="0001-26-000003",
                line_no=1,
                symbol="NVDA",
                filing_date=today,
                txn_date=today - timedelta(days=1),
                insider_name="STEVENS MARK A",
                insider_cik="1214156",
                officer_title=None,
                role="Director",
                txn_code="A",
                action="other",
                shares=Decimal("50"),
                price=None,
                value=None,
                shares_after=Decimal("5000"),
                is_10b5_1=False,
                is_amendment=False,
                source="sec_edgar",
            ),
            InsiderTxn(
                accession_no="0001-26-000004",
                line_no=1,
                symbol="OLD",
                filing_date=today,
                txn_date=today - timedelta(days=1),
                insider_name="OLD INSIDER",
                insider_cik="999999",
                officer_title="Director",
                role="Director",
                txn_code="P",
                action="buy",
                shares=Decimal("100"),
                price=Decimal("50"),
                value=Decimal("5000"),
                shares_after=Decimal("1000"),
                is_10b5_1=False,
                is_amendment=False,
                source="fixtures",
            ),
        ]
    )
    session.add_all(
        [
            Holder(
                symbol="NVDA",
                report_period=date(today.year, 9, 30),
                institution_cik="0000102909",
                institution="VANGUARD GROUP INC",
                shares=Decimal("1000000"),
                value=Decimal("180000000"),
                qoq_change_pct=None,
                rank=1,
                source="yfinance",
            ),
            Holder(
                symbol="OLD",
                report_period=date(today.year, 9, 30),
                institution_cik="999999",
                institution="OLD HOLDINGS LLC",
                shares=Decimal("1000"),
                value=Decimal("50000"),
                qoq_change_pct=None,
                rank=1,
                source="fixtures",
            ),
        ]
    )
    await session.commit()


@pytest_asyncio.fixture
async def seeded(app):  # type: ignore[no-untyped-def]
    async with app.state.db.session() as session:
        await seed_market_data(session)
    return app


@pytest_asyncio.fixture
async def client(seeded) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=seeded)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
