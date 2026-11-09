"""AC-03/AC-04: quote fallback and all-provider outage behaviour."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.config import Settings, load_runtime_config
from app.core.errors import ProviderError
from app.db.models import IngestRun, Quote
from app.providers.base import QuoteData
from app.providers.registry import ProviderRegistry
from app.services.freshness import build_freshness
from app.services.ingest import active_tickers, ingest_quotes


class StubProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]:
        return []

    async def fetch_bars(self, symbol: str, start: object, end: object) -> list[QuoteData]:
        return []


class FailingProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]:
        raise ProviderError(f"{self.name}: injected outage")


class WorkingProvider:
    name = "finnhub"

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]:
        moment = datetime.now(UTC)
        return [
            QuoteData(
                symbol=symbol,
                price=Decimal("199.99"),
                change_pct=Decimal("3.33"),
                as_of=moment,
                source=self.name,
                delayed=True,
            )
            for symbol in symbols
        ]


def test_disable_removes_named_providers_from_every_chain() -> None:
    registry = ProviderRegistry(
        quotes=[StubProvider("alpaca"), StubProvider("finnhub")],
        bars=[StubProvider("alpaca"), StubProvider("yfinance")],
        insiders=[StubProvider("sec_edgar"), StubProvider("ALPACA")],
        holders=[StubProvider("yfinance")],
    )

    registry.disable([" alpaca "])

    assert [provider.name for provider in registry.quotes] == ["finnhub"]
    assert [provider.name for provider in registry.bars] == ["yfinance"]
    assert [provider.name for provider in registry.insiders] == ["sec_edgar"]
    assert [provider.name for provider in registry.holders] == ["yfinance"]


def test_runtime_config_reads_disabled_providers_from_yaml_then_env(tmp_path: Path) -> None:
    config_path = tmp_path / "smm.yaml"
    config_path.write_text("disabled_providers:\n  - alpaca\n", encoding="utf-8")

    from_yaml = load_runtime_config(
        Settings(config_file=str(config_path), disabled_providers="finnhub")
    )
    assert from_yaml.disabled_providers == ["alpaca"]

    without_yaml = load_runtime_config(
        Settings(config_file=str(tmp_path / "missing.yaml"), disabled_providers="Alpaca, finnhub ")
    )
    assert without_yaml.disabled_providers == ["alpaca", "finnhub"]


async def test_quote_fallback_uses_the_next_provider_and_records_its_source(
    client: AsyncClient,
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    registry = ProviderRegistry(quotes=[FailingProvider("alpaca"), WorkingProvider()])

    async with app.state.db.session() as session:
        symbols = [ticker.symbol for ticker in await active_tickers(session)]
        written = await ingest_quotes(session, registry, symbols)
        quotes = list(await session.scalars(select(Quote)))
        run = await session.scalar(
            select(IngestRun).where(IngestRun.job == "quotes").order_by(IngestRun.id.desc())
        )

    assert written == len(symbols)
    # Seeded fixtures can hold quote rows for symbols outside the active watchlist.
    assert {row.source for row in quotes if row.symbol in symbols} == {"finnhub"}
    assert run is not None
    assert run.provider == "finnhub"
    assert run.status == "ok"
    assert run.rows == len(symbols)

    body = (await client.get("/api/dashboard")).json()
    assert body["quotes"]["NVDA"]["source"] == "finnhub"
    assert body["quotes"]["NVDA"]["price"] == pytest.approx(199.99)
    assert body["freshness"]["quotes"]["stale"] is False


async def test_all_quote_providers_failed_keeps_last_good_and_reports_stale(
    client: AsyncClient,
) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    registry = ProviderRegistry(
        quotes=[FailingProvider("alpaca"), FailingProvider("finnhub")],
    )

    async with app.state.db.session() as session:
        before = {row.symbol: row.price for row in await session.scalars(select(Quote))}
        await session.execute(update(Quote).values(as_of=datetime.now(UTC) - timedelta(hours=1)))
        await session.commit()

    async with app.state.db.session() as session:
        with pytest.raises(ProviderError, match="all quote providers failed"):
            await ingest_quotes(session, registry, ["NVDA"])
        after = {row.symbol: row.price for row in await session.scalars(select(Quote))}
        freshness = await build_freshness(session, app.state.settings, app.state.config)

    assert after == before
    assert freshness["quotes"].stale is True

    response = await client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["quotes"]["NVDA"]["price"] == float(before["NVDA"])
    assert body["freshness"]["quotes"]["stale"] is True
    assert len(body["signals"]) > 0
