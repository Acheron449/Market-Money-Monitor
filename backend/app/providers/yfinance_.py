"""yfinance adapter: unofficial, pinned, isolated, never the only source (AGENTS.md §6)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import yfinance as yf

from app.core.errors import ProviderError
from app.providers.base import BarData, HolderData, InsiderTxnData, QuoteData
from app.services.classification import classify, normalise_role


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except ArithmeticError:
        return None
    return result if result.is_finite() else None


class YFinanceClient:
    name = "yfinance"

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]:
        return await asyncio.to_thread(self._quotes_sync, list(symbols))

    def _quotes_sync(self, symbols: list[str]) -> list[QuoteData]:
        quotes: list[QuoteData] = []
        for symbol in symbols:
            try:
                info = yf.Ticker(symbol).fast_info
                price = _dec(info.get("last_price"))
                previous = _dec(info.get("previous_close"))
            except Exception as exc:  # yfinance raises many types
                raise ProviderError(f"yfinance {symbol}: {exc}") from exc
            if price is None:
                continue
            change = None
            if previous and previous != 0:
                change = ((price - previous) / previous * 100).quantize(Decimal("0.01"))
            quotes.append(
                QuoteData(
                    symbol=symbol,
                    price=price,
                    change_pct=change,
                    as_of=datetime.now(UTC),
                    source=self.name,
                    delayed=True,
                )
            )
        return quotes

    async def fetch_bars(self, symbol: str, start: date, end: date) -> list[BarData]:
        return await asyncio.to_thread(self._bars_sync, symbol, start, end)

    def _bars_sync(self, symbol: str, start: date, end: date) -> list[BarData]:
        try:
            frame = yf.Ticker(symbol).history(
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1d",
                auto_adjust=True,
            )
        except Exception as exc:
            raise ProviderError(f"yfinance bars {symbol}: {exc}") from exc
        bars: list[BarData] = []
        for index, row in frame.iterrows():
            close = _dec(row.get("Close"))
            if close is None:
                continue
            day = index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])
            bars.append(
                BarData(
                    symbol=symbol,
                    date=day,
                    close=close,
                    source=self.name,
                    open=_dec(row.get("Open")),
                    high=_dec(row.get("High")),
                    low=_dec(row.get("Low")),
                    volume=int(row.get("Volume") or 0) or None,
                )
            )
        return bars

    async def fetch_holders(self, symbol: str) -> list[HolderData]:
        return await asyncio.to_thread(self._holders_sync, symbol)

    def _holders_sync(self, symbol: str) -> list[HolderData]:
        try:
            frame = yf.Ticker(symbol).institutional_holders
        except Exception as exc:
            raise ProviderError(f"yfinance holders {symbol}: {exc}") from exc
        if frame is None or frame.empty:
            return []

        rows: list[HolderData] = []
        for rank, (_, row) in enumerate(frame.iterrows(), start=1):
            shares = _dec(row.get("Shares"))
            value = _dec(row.get("Value"))
            if shares is None or value is None:
                continue
            reported = row.get("Date Reported")
            report_period = _quarter_end(reported)
            institution = str(row.get("Holder") or "Unknown")
            rows.append(
                HolderData(
                    symbol=symbol,
                    institution=institution,
                    institution_cik=f"yf-{_slug(institution)}",
                    shares=shares,
                    value=value,
                    report_period=report_period,
                    rank=rank,
                    source=self.name,
                )
            )
        return rows

    async def fetch_transactions(
        self, symbol: str, cik: str | None, since: date
    ) -> list[InsiderTxnData]:
        return await asyncio.to_thread(self._insiders_sync, symbol, since)

    def _insiders_sync(self, symbol: str, since: date) -> list[InsiderTxnData]:
        try:
            frame = yf.Ticker(symbol).insider_transactions
        except Exception as exc:
            raise ProviderError(f"yfinance insiders {symbol}: {exc}") from exc
        if frame is None or frame.empty:
            return []

        rows: list[InsiderTxnData] = []
        for index, (_, row) in enumerate(frame.iterrows(), start=1):
            code = str(row.get("Transaction") or "")[:1].upper()
            txn_date = _as_date(row.get("Start Date"))
            if not code or txn_date is None or txn_date < since:
                continue
            shares = _dec(row.get("Shares")) or Decimal("0")
            value = _dec(row.get("Value"))
            price = (value / shares) if value and shares else None
            info = classify(code)
            rows.append(
                InsiderTxnData(
                    symbol=symbol,
                    accession_no=f"yfinance-{symbol}-{index}-{txn_date.isoformat()}",
                    line_no=index,
                    filing_date=txn_date,
                    txn_date=txn_date,
                    insider_name=str(row.get("Insider") or "Unknown"),
                    insider_cik=None,
                    officer_title=None,
                    role=normalise_role(officer_title=None),
                    txn_code=code,
                    action=info.action,
                    shares=shares,
                    price=price,
                    value=value,
                    shares_after=_dec(row.get("Shares Total")),
                    is_10b5_1=False,
                    is_amendment=False,
                    source=self.name,
                )
            )
        return rows


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        result = value.date()
        return result if isinstance(result, date) else None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _quarter_end(value: Any) -> date:
    day = _as_date(value)
    if day is None:
        today = date.today()
        day = today
    quarter = (day.month - 1) // 3
    end_month = quarter * 3 + 3
    day = date(day.year, end_month, 1)
    next_month = date(day.year + (day.month == 12), (day.month % 12) + 1, 1)
    from datetime import timedelta

    return next_month - timedelta(days=1)


def _slug(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name)
    return "-".join(part for part in cleaned.split("-") if part)[:24]
