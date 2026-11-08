"""Provider registry: ordered fallback chains built from configuration (ING-08)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config import RuntimeConfig, Settings
from app.core.breaker import CircuitBreaker
from app.core.http import HttpClient
from app.core.ratelimit import RateLimiter
from app.providers.alpaca import AlpacaClient
from app.providers.base import BarProvider, HolderProvider, InsiderProvider, QuoteProvider
from app.providers.finnhub import FinnhubClient
from app.providers.sec_edgar import SecEdgarClient
from app.providers.yfinance_ import YFinanceClient


def _client(settings: Settings, name: str, *, rps: float) -> HttpClient:
    agent = settings.sec_user_agent if name == "sec_edgar" else "Smart Money Monitor"
    return HttpClient(
        user_agent=agent if name == "sec_edgar" else None,
        limiter=RateLimiter(rps),
        breaker=CircuitBreaker(name),
        retries=2,
        timeout=15.0,
    )


@dataclass
class ProviderRegistry:
    quotes: list[QuoteProvider] = field(default_factory=list)
    bars: list[BarProvider] = field(default_factory=list)
    insiders: list[InsiderProvider] = field(default_factory=list)
    holders: list[HolderProvider] = field(default_factory=list)
    directory: SecEdgarClient | None = None
    _clients: list[HttpClient] = field(default_factory=list)

    async def close(self) -> None:
        for client in self._clients:
            await client.close()


def build_registry(settings: Settings, config: RuntimeConfig) -> ProviderRegistry:
    registry = ProviderRegistry()
    if not settings.providers_enabled:
        # Offline/demo mode: no network providers, refreshes become no-ops.
        return registry

    sec_http = _client(settings, "sec_edgar", rps=min(settings.sec_max_rps, 5.0))
    registry._clients.append(sec_http)
    sec = SecEdgarClient(sec_http)
    registry.directory = sec
    registry.insiders.append(sec)

    if settings.alpaca_key_id and settings.alpaca_secret_key:
        alpaca_http = _client(settings, "alpaca", rps=3.0)
        registry._clients.append(alpaca_http)
        alpaca = AlpacaClient(
            alpaca_http,
            key_id=settings.alpaca_key_id,
            secret=settings.alpaca_secret_key,
            feed=settings.alpaca_feed,
        )
        registry.quotes.append(alpaca)
        registry.bars.append(alpaca)

    if settings.finnhub_api_key:
        finnhub_http = _client(settings, "finnhub", rps=1.5)
        registry._clients.append(finnhub_http)
        finnhub = FinnhubClient(finnhub_http, api_key=settings.finnhub_api_key)
        registry.quotes.append(finnhub)
        registry.insiders.append(finnhub)

    yfinance_http = _client(settings, "yfinance", rps=0.5)
    registry._clients.append(yfinance_http)
    yfinance_client = YFinanceClient()
    registry.quotes.append(yfinance_client)
    registry.bars.append(yfinance_client)
    registry.holders.append(yfinance_client)
    registry.insiders.append(yfinance_client)

    order = config.provider_order or {}

    def _sort(items: list[Any], kind: str) -> None:
        preferred = order.get(kind) or []
        if not preferred:
            return
        ranking = {name: index for index, name in enumerate(preferred)}

        def key(item: Any) -> int:
            name = getattr(item, "name", "")
            return ranking.get(str(name), len(ranking))

        items.sort(key=key)

    _sort(registry.quotes, "quotes")
    _sort(registry.bars, "bars")
    _sort(registry.insiders, "insiders")
    _sort(registry.holders, "holders")
    return registry
