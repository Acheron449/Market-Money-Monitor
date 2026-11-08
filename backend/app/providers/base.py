"""Provider interfaces and the domain transfer objects they return (ING-01)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class QuoteData:
    symbol: str
    price: Decimal
    change_pct: Decimal | None
    as_of: datetime
    source: str
    delayed: bool = False


@dataclass(frozen=True, slots=True)
class BarData:
    symbol: str
    date: date
    close: Decimal
    source: str
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: int | None = None


@dataclass(frozen=True, slots=True)
class FilingRef:
    accession_no: str
    cik: str
    symbol: str
    filing_date: date
    form_type: str
    document_url: str


@dataclass(frozen=True, slots=True)
class InsiderTxnData:
    symbol: str
    accession_no: str
    line_no: int
    filing_date: date
    txn_date: date
    insider_name: str
    insider_cik: str | None
    officer_title: str | None
    role: str
    txn_code: str
    action: str
    shares: Decimal
    price: Decimal | None
    value: Decimal | None
    shares_after: Decimal | None
    is_10b5_1: bool
    is_amendment: bool
    source: str
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HolderData:
    symbol: str
    institution: str
    institution_cik: str
    shares: Decimal
    value: Decimal
    report_period: date
    rank: int
    source: str
    prev_shares: Decimal | None = None
    qoq_change_pct: Decimal | None = None


@runtime_checkable
class QuoteProvider(Protocol):
    name: str

    async def fetch_quotes(self, symbols: Sequence[str]) -> list[QuoteData]: ...


@runtime_checkable
class BarProvider(Protocol):
    name: str

    async def fetch_bars(self, symbol: str, start: date, end: date) -> list[BarData]: ...


@runtime_checkable
class InsiderProvider(Protocol):
    name: str

    async def fetch_transactions(
        self, symbol: str, cik: str | None, since: date
    ) -> list[InsiderTxnData]: ...


@runtime_checkable
class HolderProvider(Protocol):
    name: str

    async def fetch_holders(self, symbol: str) -> list[HolderData]: ...


@runtime_checkable
class TickerDirectoryProvider(Protocol):
    name: str

    async def company_tickers(self) -> dict[str, dict[str, str]]: ...
