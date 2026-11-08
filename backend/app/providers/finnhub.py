"""Finnhub: quote fallback and a thinner insider fallback (ING-08)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.core.errors import ProviderError
from app.core.http import HttpClient
from app.providers.base import InsiderTxnData, QuoteData
from app.services.classification import classify, normalise_role

BASE = "https://finnhub.io/api/v1"


def _dec(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None


class FinnhubClient:
    name = "finnhub"

    def __init__(self, http: HttpClient, *, api_key: str) -> None:
        self._http = http
        self._token = api_key

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]:
        quotes: list[QuoteData] = []
        for symbol in symbols:
            payload = await self._http.get_json(
                f"{BASE}/quote", params={"symbol": symbol, "token": self._token}
            )
            if not isinstance(payload, dict):
                continue
            price = _dec(payload.get("c"))
            if price is None or price == 0:
                continue
            change = _dec(payload.get("dp"))
            timestamp = payload.get("t")
            as_of = (
                datetime.fromtimestamp(int(timestamp), tz=UTC)
                if isinstance(timestamp, int | float) and timestamp
                else datetime.now(UTC)
            )
            quotes.append(
                QuoteData(
                    symbol=symbol,
                    price=price,
                    change_pct=change,
                    as_of=as_of,
                    source=self.name,
                    delayed=True,
                )
            )
        return quotes

    async def fetch_transactions(
        self, symbol: str, cik: str | None, since: date
    ) -> list[InsiderTxnData]:
        payload = await self._http.get_json(
            f"{BASE}/stock/insider-transactions",
            params={
                "symbol": symbol,
                "from": since.isoformat(),
                "to": date.today().isoformat(),
                "token": self._token,
            },
        )
        if not isinstance(payload, dict):
            raise ProviderError(f"finnhub insiders {symbol}: unexpected payload")

        rows: list[InsiderTxnData] = []
        for index, raw in enumerate(payload.get("data") or [], start=1):
            code = str(raw.get("transactionCode") or "").upper()
            if not code:
                continue
            change = _dec(raw.get("change")) or Decimal("0")
            shares = abs(change)
            price = _dec(raw.get("transactionPrice")) or None
            info = classify(code)
            txn_date = _parse_date(raw.get("transactionDate"))
            rows.append(
                InsiderTxnData(
                    symbol=symbol,
                    accession_no=f"finnhub-{symbol}-{index}-{txn_date.isoformat()}",
                    line_no=index,
                    filing_date=_parse_date(raw.get("filingDate")),
                    txn_date=txn_date,
                    insider_name=str(raw.get("name") or "Unknown"),
                    insider_cik=None,
                    officer_title=None,
                    role=normalise_role(officer_title=None),
                    txn_code=code,
                    action=info.action,
                    shares=shares,
                    price=price,
                    value=(shares * price) if price else None,
                    shares_after=_dec(raw.get("share")),
                    is_10b5_1=bool(raw.get("is10b5One")),
                    is_amendment=False,
                    source=self.name,
                )
            )
        return rows


def _parse_date(value: object) -> date:
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return date.today()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
