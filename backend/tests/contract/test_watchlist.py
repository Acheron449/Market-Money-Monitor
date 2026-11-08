"""UI-12 watchlist contract: auth, writes, validation, ordering and persistence."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.services.ingest import seed_watchlist

TOKEN = {"Authorization": "Bearer test-token"}


async def test_get_watchlist_returns_active_tickers_in_order(client: AsyncClient) -> None:
    response = await client.get("/api/watchlist")
    assert response.status_code == 200
    assert response.json() == {"tickers": ["NVDA", "AAPL"]}


async def test_watchlist_write_requires_the_admin_token(client: AsyncClient) -> None:
    denied = await client.put("/api/watchlist", json={"tickers": ["NVDA"]})
    assert denied.status_code == 401
    assert denied.json()["code"] == "unauthorized"

    allowed = await client.put("/api/watchlist", json={"tickers": ["NVDA", "AAPL"]}, headers=TOKEN)
    assert allowed.status_code == 200


async def test_authenticated_write_activates_data_for_every_read_path(
    client: AsyncClient,
) -> None:
    response = await client.put("/api/watchlist", json={"tickers": ["OLD", "NVDA"]}, headers=TOKEN)
    assert response.status_code == 200
    assert response.json() == {"tickers": ["OLD", "NVDA"]}

    dashboard = (await client.get("/api/dashboard")).json()
    assert [signal["ticker"] for signal in dashboard["signals"]] == ["OLD", "NVDA"]
    assert dashboard["signals"][0] == {
        "ticker": "OLD",
        "netValue": 15000.0,
        "txnCount": 3,
        "starredCount": 0,
        "clusterBuy": True,
    }
    assert dashboard["quotes"]["OLD"]["price"] == 50.0
    assert [row["ticker"] for row in dashboard["tape"]].count("OLD") == 3

    history = (await client.get("/api/history/OLD")).json()
    assert history == [{"date": history[0]["date"], "close": 48.0}]
    holders = (await client.get("/api/holders/OLD")).json()
    assert holders[0]["institution"] == "OLD HOLDINGS LLC"

    # Removing a ticker deactivates it and removes it from the dashboard while
    # keeping its stored history available to the read endpoints.
    removed = await client.put("/api/watchlist", json={"tickers": ["NVDA"]}, headers=TOKEN)
    assert removed.json() == {"tickers": ["NVDA"]}
    dashboard = (await client.get("/api/dashboard")).json()
    assert [signal["ticker"] for signal in dashboard["signals"]] == ["NVDA"]
    assert "OLD" not in dashboard["quotes"]
    assert all(row["ticker"] != "OLD" for row in dashboard["tape"])
    assert (await client.get("/api/history/OLD")).status_code == 200


async def test_write_normalises_deduplicates_and_reorders(client: AsyncClient) -> None:
    response = await client.put(
        "/api/watchlist",
        json={"tickers": [" aapl ", "NVDA", "nvda", "AAPL"]},
        headers=TOKEN,
    )
    assert response.status_code == 200
    assert response.json() == {"tickers": ["AAPL", "NVDA"]}

    reordered = await client.put(
        "/api/watchlist", json={"tickers": ["NVDA", "AAPL"]}, headers=TOKEN
    )
    assert reordered.json() == {"tickers": ["NVDA", "AAPL"]}
    assert (await client.get("/api/watchlist")).json() == {"tickers": ["NVDA", "AAPL"]}
    dashboard = (await client.get("/api/dashboard")).json()
    assert [signal["ticker"] for signal in dashboard["signals"]] == ["NVDA", "AAPL"]


async def test_validation_rejects_malformed_empty_oversized_and_unknown(
    client: AsyncClient,
) -> None:
    malformed = await client.put(
        "/api/watchlist", json={"tickers": ["not a ticker"]}, headers=TOKEN
    )
    assert malformed.status_code == 422
    assert malformed.json()["code"] == "invalid_ticker"

    unknown = await client.put("/api/watchlist", json={"tickers": ["ZZZZ"]}, headers=TOKEN)
    assert unknown.status_code == 422
    assert unknown.json() == {
        "code": "unknown_ticker",
        "message": "ZZZZ is not in the known ticker universe",
    }

    empty = await client.put("/api/watchlist", json={"tickers": []}, headers=TOKEN)
    assert empty.status_code == 422
    assert empty.json()["code"] == "empty_watchlist"

    oversized = await client.put(
        "/api/watchlist",
        json={"tickers": [f"T{index:02d}" for index in range(51)]},
        headers=TOKEN,
    )
    assert oversized.status_code == 422
    assert oversized.json()["code"] == "watchlist_too_large"

    # A rejected write leaves the previous watchlist untouched.
    assert (await client.get("/api/watchlist")).json() == {"tickers": ["NVDA", "AAPL"]}


async def test_remote_writes_require_the_admin_token(seeded) -> None:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=seeded, client=("203.0.113.9", 50000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as remote:
        assert (await remote.get("/api/watchlist")).status_code == 200

        denied = await remote.put("/api/watchlist", json={"tickers": ["NVDA"]})
        assert denied.status_code == 401
        assert denied.json()["code"] == "unauthorized"

        allowed = await remote.put(
            "/api/watchlist", json={"tickers": ["OLD", "NVDA"]}, headers=TOKEN
        )
        assert allowed.status_code == 200
        assert allowed.json() == {"tickers": ["OLD", "NVDA"]}


async def test_replaced_watchlist_survives_a_restart(seeded) -> None:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=seeded)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        assert (
            await http.put("/api/watchlist", json={"tickers": ["OLD", "NVDA"]}, headers=TOKEN)
        ).is_success

    restarted = create_app(seeded.state.settings)
    await restarted.state.db.create_all()
    try:
        # Start-up seeding must not overwrite a database-owned watchlist.
        async with restarted.state.db.session() as session:
            await seed_watchlist(session, restarted.state.config)

        async with AsyncClient(
            transport=ASGITransport(app=restarted), base_url="http://testserver"
        ) as http:
            assert (await http.get("/api/watchlist")).json() == {"tickers": ["OLD", "NVDA"]}
            dashboard = (await http.get("/api/dashboard")).json()
            assert [signal["ticker"] for signal in dashboard["signals"]] == ["OLD", "NVDA"]
    finally:
        for task in list(restarted.state.tasks):
            task.cancel()
        await restarted.state.registry.close()
        await restarted.state.db.dispose()
