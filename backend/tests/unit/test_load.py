"""AC-05: the dashboard meets NFR-01 under 50 concurrent users."""

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
from app.db.models import InsiderTxn, PriceBar, Quote, Ticker
from app.main import create_app
from app.services.load_test import BUDGET_P95_MS, percentile, run_load, warm_up

SYMBOLS = ("NVDA", "AAPL", "TSLA", "AMZN", "META", "AMD", "PLTR", "COIN")
TXNS_PER_SYMBOL = 10
BARS_PER_SYMBOL = 130


async def seed_nfr_data(session: AsyncSession) -> None:
    """Seed the NFR-01 shape: eight tickers, 6 months of bars and a full tape."""

    today = date.today()
    session.add_all(
        [
            Ticker(
                symbol=symbol,
                cik=f"000{symbol}0",
                name=f"{symbol} CORP",
                exchange="NASDAQ",
                active=True,
                sort_order=index,
            )
            for index, symbol in enumerate(SYMBOLS)
        ]
    )
    session.add_all(
        [
            Quote(
                symbol=symbol,
                price=Decimal("100") + Decimal(index),
                change_pct=Decimal("1.25"),
                as_of=datetime.now(UTC),
                source="fixtures",
                delayed=True,
            )
            for index, symbol in enumerate(SYMBOLS)
        ]
    )
    session.add_all(
        [
            PriceBar(
                symbol=symbol,
                date=today - timedelta(days=offset),
                close=Decimal("100") + Decimal(offset % 17),
                source="fixtures",
            )
            for symbol in SYMBOLS
            for offset in range(BARS_PER_SYMBOL)
        ]
    )
    session.add_all(
        [
            InsiderTxn(
                accession_no=f"{symbol}-26-{index:04d}",
                line_no=1,
                symbol=symbol,
                filing_date=today,
                txn_date=today - timedelta(days=index % 120 + 1),
                insider_name=f"{symbol} INSIDER {index}",
                insider_cik=f"{900000 + index}",
                officer_title="Chief Executive Officer" if index % 5 == 0 else None,
                role="CEO" if index % 5 == 0 else "Director",
                txn_code="P" if index % 2 == 0 else "S",
                action="buy" if index % 2 == 0 else "sell",
                shares=Decimal("1000"),
                price=Decimal("100"),
                value=Decimal("100000"),
                shares_after=Decimal("50000"),
                is_10b5_1=index % 7 == 0,
                is_amendment=False,
                source="fixtures",
            )
            for symbol in SYMBOLS
            for index in range(TXNS_PER_SYMBOL)
        ]
    )
    await session.commit()


@pytest_asyncio.fixture
async def nfr_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'nfr.db'}",
        scheduler_enabled=False,
        sec_user_agent="Smart Money Monitor tests test@example.com",
    )
    application = create_app(settings)
    await application.state.db.create_all()
    async with application.state.db.session() as session:
        await seed_nfr_data(session)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://nfrtest") as client:
        yield client

    for task in list(application.state.tasks):
        task.cancel()
    await application.state.registry.close()
    await application.state.db.dispose()


def test_percentile_uses_nearest_rank() -> None:
    samples = [float(value) for value in range(1, 101)]
    assert percentile(samples, 50) == 50
    assert percentile(samples, 95) == 95
    assert percentile(samples, 99) == 99
    assert percentile([7.5], 95) == 7.5
    with pytest.raises(ValueError, match="at least one sample"):
        percentile([], 95)
    with pytest.raises(ValueError, match="quantile"):
        percentile(samples, 0)


async def test_run_load_validates_arguments() -> None:
    async def fetch() -> bool:
        return True

    with pytest.raises(ValueError, match="users"):
        await run_load(fetch, users=0, requests_per_user=1)
    with pytest.raises(ValueError, match="requests_per_user"):
        await run_load(fetch, users=1, requests_per_user=0)
    with pytest.raises(ValueError, match="think_time_ms"):
        await run_load(fetch, users=1, requests_per_user=1, think_time_ms=-1)
    with pytest.raises(ValueError, match="ramp_ms"):
        await run_load(fetch, users=1, requests_per_user=1, ramp_ms=-1)
    with pytest.raises(ValueError, match="warm-up"):
        await warm_up(fetch, -1)


async def test_dashboard_meets_nfr_01_at_fifty_concurrent_users(
    nfr_client: AsyncClient,
) -> None:
    async def fetch() -> bool:
        response = await nfr_client.get("/api/dashboard")
        return response.status_code == 200

    await warm_up(fetch, 20)
    result = await run_load(
        fetch,
        users=50,
        requests_per_user=3,
        think_time_ms=1000,
        ramp_ms=20,
    )

    assert result.requests == 150
    assert result.errors == 0
    assert result.throughput_rps > 0
    assert result.p95_ms <= BUDGET_P95_MS, result.summary()

    body = (await nfr_client.get("/api/dashboard")).json()
    assert len(body["signals"]) == len(SYMBOLS)
    assert len(body["tape"]) == len(SYMBOLS) * TXNS_PER_SYMBOL
    assert body["lookbackMonths"] == 6
