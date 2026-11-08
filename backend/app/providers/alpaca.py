"""Alpaca market data: snapshots for quotes, daily bars (ING-05, ING-06)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.core.errors import ProviderError
from app.core.http import HttpClient
from app.providers.base import BarData, QuoteData

DATA_HOST = "https://data.alpaca.markets/v2/stocks"


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


class AlpacaClient:
    name = "alpaca"

    def __init__(self, http: HttpClient, *, key_id: str, secret: str, feed: str = "iex") -> None:
        self._http = http
        self._headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret,
        }
        self._feed = feed

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]:
        if not symbols:
            return []
        payload = await self._http.get_json(
            f"{DATA_HOST}/snapshots",
            params={"symbols": ",".join(symbols), "feed": self._feed},
            headers=self._headers,
        )
        if not isinstance(payload, dict):
            raise ProviderError("alpaca snapshots: unexpected payload")

        quotes: list[QuoteData] = []
        for symbol in symbols:
            snapshot = payload.get(symbol)
            if not isinstance(snapshot, dict):
                continue
            trade = snapshot.get("latestTrade") or {}
            daily = snapshot.get("dailyBar") or {}
            previous = snapshot.get("prevDailyBar") or {}
            price = _dec(trade.get("p")) or _dec(daily.get("c"))
            if price is None:
                continue
            prev_close = _dec(previous.get("c")) or _dec(daily.get("o"))
            change = None
            if prev_close and prev_close != 0:
                change = ((price - prev_close) / prev_close * 100).quantize(Decimal("0.01"))
            timestamp = trade.get("t") or daily.get("t")
            as_of = _parse_timestamp(timestamp)
            quotes.append(
                QuoteData(
                    symbol=symbol,
                    price=price,
                    change_pct=change,
                    as_of=as_of,
                    source=self.name,
                    delayed=self._feed != "sip",
                )
            )
        return quotes

    async def fetch_bars(self, symbol: str, start: date, end: date) -> list[BarData]:
        bars: list[BarData] = []
        token: str | None = None
        while True:
            params: dict[str, Any] = {
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "adjustment": "split",
                "feed": self._feed,
                "limit": 10000,
            }
            if token:
                params["page_token"] = token
            payload = await self._http.get_json(
                f"{DATA_HOST}/{symbol}/bars", params=params, headers=self._headers
            )
            if not isinstance(payload, dict):
                raise ProviderError(f"alpaca bars {symbol}: unexpected payload")
            for raw in payload.get("bars") or []:
                close = _dec(raw.get("c"))
                if close is None:
                    continue
                bars.append(
                    BarData(
                        symbol=symbol,
                        date=_parse_date(raw.get("t")),
                        close=close,
                        source=self.name,
                        open=_dec(raw.get("o")),
                        high=_dec(raw.get("h")),
                        low=_dec(raw.get("l")),
                        volume=int(raw.get("v") or 0) or None,
                    )
                )
            token = payload.get("next_page_token")
            if not token:
                break
        return bars


def _parse_date(value: object) -> date:
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ProviderError(f"alpaca: unparseable bar timestamp {value!r}")


def _parse_timestamp(value: object) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    return datetime.now(UTC)


async def collect(stream: AsyncIterator[QuoteData]) -> list[QuoteData]:
    return [quote async for quote in stream]
