"""Contract and runner coverage for ADM-03 alert history."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import AlertEvent
from app.jobs.runner import run_form4
from app.providers.base import InsiderTxnData
from app.providers.registry import ProviderRegistry


async def test_alert_history_contract_orders_and_limits(client: AsyncClient, seeded: Any) -> None:
    now = datetime.now(UTC)
    async with seeded.state.db.session() as session:
        session.add_all(
            [
                AlertEvent(
                    dedupe_key="test:old",
                    kind="large_transaction",
                    symbol="NVDA",
                    title="Old alert",
                    body="old",
                    channels="webhook",
                    status="delivered",
                    created_at=now - timedelta(minutes=1),
                ),
                AlertEvent(
                    dedupe_key="test:new",
                    kind="ceo_cfo_buy",
                    symbol="AAPL",
                    title="New alert",
                    body="new",
                    channels="",
                    status="recorded",
                    created_at=now,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/alerts")
    assert response.status_code == 200
    rows = response.json()
    assert [row["title"] for row in rows] == ["New alert", "Old alert"]
    assert set(rows[0]) == {
        "id",
        "kind",
        "symbol",
        "title",
        "body",
        "createdAt",
        "channels",
        "status",
    }
    assert rows[0]["channels"] == []
    assert rows[0]["status"] == "recorded"
    assert rows[1]["channels"] == ["webhook"]
    assert rows[1]["createdAt"].endswith("+00:00")

    limited = await client.get("/api/alerts?limit=1")
    assert limited.status_code == 200
    assert [row["title"] for row in limited.json()] == ["New alert"]

    assert (await client.get("/api/alerts?limit=0")).status_code == 422
    assert (await client.get("/api/alerts?limit=101")).status_code == 422


class _InsiderProvider:
    name = "test-insiders"

    def __init__(self, row: InsiderTxnData) -> None:
        self.row = row

    async def fetch_transactions(
        self, symbol: str, cik: str | None, since: date
    ) -> list[InsiderTxnData]:
        return [self.row] if symbol == "NVDA" else []


async def test_run_form4_persists_alerts_for_new_insider_rows(seeded: Any) -> None:
    today = date.today()
    row = InsiderTxnData(
        symbol="NVDA",
        accession_no="0001-26-009999",
        line_no=1,
        filing_date=today,
        txn_date=today,
        insider_name="ALERT TEST CEO",
        insider_cik="999999",
        officer_title="Chief Executive Officer",
        role="CEO",
        txn_code="P",
        action="buy",
        shares=Decimal("1000"),
        price=Decimal("2500"),
        value=Decimal("2500000"),
        shares_after=None,
        is_10b5_1=False,
        is_amendment=False,
        source="tests",
    )
    seeded.state.registry = ProviderRegistry(insiders=[_InsiderProvider(row)])

    await run_form4(seeded)

    async with seeded.state.db.session() as session:
        rows = list(await session.scalars(select(AlertEvent).order_by(AlertEvent.id)))
    assert {event.kind for event in rows} == {"ceo_cfo_buy", "large_transaction"}
    assert all(event.symbol == "NVDA" for event in rows)
    assert all(event.status == "recorded" for event in rows)
