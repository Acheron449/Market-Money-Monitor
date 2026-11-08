"""SEC EDGAR: submissions JSON and Form 4 XML (ING-02, ING-03)."""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any

from app.core.errors import ProviderError
from app.core.http import HttpClient
from app.parsers.form4 import parse_form4
from app.providers.base import FilingRef, InsiderTxnData, TickerDirectoryProvider

DATA_HOST = "https://data.sec.gov"
ARCHIVE_HOST = "https://www.sec.gov/Archives/edgar/data"
FORM_TYPES = frozenset({"4", "4/A"})


class SecEdgarClient(TickerDirectoryProvider):
    """Authoritative insider source. Stays at or under 5 requests per second."""

    name = "sec_edgar"

    def __init__(self, http: HttpClient, *, cache_ttl: float = 300.0) -> None:
        self._http = http
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Any]] = {}

    async def _cached_json(self, url: str) -> Any:
        cached = self._cache.get(url)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl:
            return cached[1]
        payload = await self._http.get_json(url)
        self._cache[url] = (now, payload)
        return payload

    async def company_tickers(self) -> dict[str, dict[str, str]]:
        payload = await self._cached_json("https://www.sec.gov/files/company_tickers.json")
        if not isinstance(payload, dict):
            raise ProviderError("company_tickers: unexpected payload")
        result: dict[str, dict[str, str]] = {}
        for entry in payload.values():
            if not isinstance(entry, dict):
                continue
            ticker = str(entry.get("ticker", "")).upper()
            if not ticker:
                continue
            result[ticker] = {
                "cik": f"{int(entry['cik_str']):010d}",
                "name": str(entry.get("title", "")),
            }
        return result

    async def submissions(self, cik: str) -> dict[str, Any]:
        payload = await self._cached_json(f"{DATA_HOST}/submissions/CIK{int(cik):010d}.json")
        if not isinstance(payload, dict):
            raise ProviderError(f"submissions {cik}: unexpected payload")
        return payload

    async def list_form4_filings(self, cik: str, symbol: str, since: date) -> list[FilingRef]:
        payload = await self.submissions(cik)
        recent = payload.get("filings", {}).get("recent", {})
        if not isinstance(recent, dict):
            return []

        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        documents = recent.get("primaryDocument", [])

        refs: list[FilingRef] = []
        for index, form in enumerate(forms):
            if str(form) not in FORM_TYPES:
                continue
            try:
                filed = date.fromisoformat(str(filing_dates[index])[:10])
            except (IndexError, ValueError):
                continue
            if filed < since:
                continue
            accession = str(accessions[index])
            document = str(documents[index])
            nodash = accession.replace("-", "")
            refs.append(
                FilingRef(
                    accession_no=accession,
                    cik=cik,
                    symbol=symbol,
                    filing_date=filed,
                    form_type=str(form),
                    document_url=f"{ARCHIVE_HOST}/{int(cik)}/{nodash}/{document}",
                )
            )
        refs.sort(key=lambda ref: ref.filing_date)
        return refs

    async def fetch_transactions(
        self, symbol: str, cik: str | None, since: date
    ) -> list[InsiderTxnData]:
        if not cik:
            raise ProviderError(f"{symbol}: no CIK known")
        rows: list[InsiderTxnData] = []
        for ref in await self.list_form4_filings(cik, symbol, since):
            xml = await self._http.get_text(ref.document_url)
            parsed = parse_form4(
                xml,
                accession_no=ref.accession_no,
                filing_date=ref.filing_date,
                source=self.name,
                fallback_symbol=symbol,
            )
            for txn in parsed.transactions:
                rows.append(txn if txn.symbol else _with_symbol(txn, symbol))
        return rows


def _with_symbol(txn: InsiderTxnData, symbol: str) -> InsiderTxnData:
    from dataclasses import replace

    return replace(txn, symbol=symbol)


def utcnow() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
