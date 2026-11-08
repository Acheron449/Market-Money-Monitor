"""Shared HTTP client: timeouts, retries with backoff, rate limit and breaker."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Any

import httpx

from app.core.breaker import CircuitBreaker
from app.core.errors import ProviderError, ProviderUnavailable, TransientHTTPError
from app.core.ratelimit import RateLimiter

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class HttpClient:
    """The only way providers talk to the network (AGENTS.md §4)."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float = 10.0,
        retries: int = 3,
        backoff: float = 0.5,
        limiter: RateLimiter | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        headers = {"User-Agent": user_agent} if user_agent else {}
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True)
        self._retries = retries
        self._backoff = backoff
        self._limiter = limiter
        self._breaker = breaker

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        if self._breaker is not None and not self._breaker.allow():
            raise ProviderUnavailable(f"{url}: circuit breaker open")

        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                if self._limiter is not None:
                    await self._limiter.acquire()
                response = await self._client.get(url, params=params, headers=headers)
                if response.status_code in RETRY_STATUS:
                    raise TransientHTTPError(f"{url}: HTTP {response.status_code}")
                response.raise_for_status()
            except (httpx.HTTPError, TransientHTTPError) as exc:
                last_error = exc
                if attempt < self._retries:
                    await asyncio.sleep(self._backoff * (2**attempt))
                continue
            if self._breaker is not None:
                self._breaker.record_success()
            return response

        if self._breaker is not None:
            self._breaker.record_failure()
        raise ProviderError(f"{url}: {last_error}") from last_error

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        response = await self.get(url, params=params, headers=headers)
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(f"{url}: invalid JSON") from exc

    async def get_text(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        response = await self.get(url, params=params, headers=headers)
        return response.text

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


def headers_from(items: Sequence[tuple[str, str]]) -> dict[str, str]:
    return {key: value for key, value in items}
