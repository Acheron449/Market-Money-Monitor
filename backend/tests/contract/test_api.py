"""Contract tests for SRS 7.1/7.2 shapes."""

from __future__ import annotations

import asyncio

from httpx import AsyncClient

from app.providers.registry import ProviderRegistry


async def test_dashboard_matches_contract(client: AsyncClient) -> None:
    response = await client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {
        "signals",
        "quotes",
        "tape",
        "lookbackMonths",
        "latestFilingDate",
        "generatedAt",
        "freshness",
    }
    assert body["lookbackMonths"] == 6

    signals = {signal["ticker"]: signal for signal in body["signals"]}
    assert set(signals) == {"NVDA", "AAPL"}
    assert signals["NVDA"] == {
        "ticker": "NVDA",
        "netValue": 50000.0,
        "txnCount": 2,
        "starredCount": 1,
        "clusterBuy": False,
    }
    assert signals["AAPL"] == {
        "ticker": "AAPL",
        "netValue": 0.0,
        "txnCount": 0,
        "starredCount": 0,
        "clusterBuy": False,
    }

    quote = body["quotes"]["NVDA"]
    assert quote["price"] == 182.5
    assert quote["changePct"] == 1.25
    assert quote["source"] == "alpaca"
    assert quote["delayed"] is True

    assert len(body["tape"]) == 3
    first = body["tape"][0]
    assert set(first) == {
        "key",
        "ticker",
        "date",
        "name",
        "role",
        "action",
        "typeLabel",
        "shares",
        "value",
        "starred",
        "is10b5_1",
    }
    award = next(row for row in body["tape"] if row["action"] == "other")
    assert award["value"] is None
    assert award["typeLabel"] == "Award / grant"

    assert body["latestFilingDate"] is not None
    assert set(body["freshness"]) == {"quotes", "filings", "bars", "holders"}
    assert set(body["freshness"]["quotes"]) == {"asOf", "stale"}


async def test_dashboard_can_exclude_10b5_1_sales_from_net(client: AsyncClient) -> None:
    default = (await client.get("/api/dashboard")).json()
    nvda = next(signal for signal in default["signals"] if signal["ticker"] == "NVDA")
    assert nvda["netValue"] == 50000.0
    assert nvda["txnCount"] == 2
    assert any(row["is10b5_1"] for row in default["tape"])

    response = await client.get("/api/dashboard?exclude10b5_1=true")
    assert response.status_code == 200
    body = response.json()
    excluded = body["signals"]
    nvda = next(signal for signal in excluded if signal["ticker"] == "NVDA")
    assert nvda == {
        "ticker": "NVDA",
        "netValue": 100000.0,
        "txnCount": 2,
        "starredCount": 1,
        "clusterBuy": False,
    }
    # The tape still carries the flagged row and its badge data.
    assert any(row["is10b5_1"] for row in body["tape"])


async def test_history_returns_ascending_closes(client: AsyncClient) -> None:
    response = await client.get("/api/history/NVDA")
    assert response.status_code == 200
    points = response.json()
    assert len(points) == 1
    assert set(points[0]) == {"date", "close"}
    assert points[0]["close"] == 180.0


async def test_unknown_ticker_is_404(client: AsyncClient) -> None:
    response = await client.get("/api/history/ZZZZ")
    assert response.status_code == 404
    assert response.json() == {"code": "unknown_ticker", "message": "ZZZZ is not in the watchlist"}


async def test_holders_contract_including_null_qoq(client: AsyncClient) -> None:
    response = await client.get("/api/holders/NVDA")
    assert response.status_code == 200
    holders = response.json()
    assert holders[0]["rank"] == 1
    assert holders[0]["institution"] == "VANGUARD GROUP INC"
    assert holders[0]["qoqChangePct"] is None
    assert holders[0]["reportPeriod"].endswith("-09-30")


async def test_refresh_is_accepted_then_throttled(client: AsyncClient) -> None:
    client._transport.app.state.registry = ProviderRegistry()  # type: ignore[attr-defined]

    first = await client.post("/api/refresh")
    assert first.status_code == 202
    assert first.json()["status"] == "accepted"
    assert first.json()["jobId"]

    app = client._transport.app  # type: ignore[attr-defined]
    while app.state.tasks:
        await asyncio.gather(*list(app.state.tasks), return_exceptions=True)

    second = await client.post("/api/refresh")
    assert second.status_code == 429
    assert second.json()["code"] == "throttled"


async def test_health_and_readiness(client: AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).json() == {"status": "ready"}
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "python" in metrics.text.lower() or "process" in metrics.text.lower()
