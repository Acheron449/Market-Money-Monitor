"""Response models for the contract in SRS 7.2."""

from __future__ import annotations

from pydantic import BaseModel


class SignalOut(BaseModel):
    ticker: str
    netValue: float
    txnCount: int
    starredCount: int


class QuoteOut(BaseModel):
    price: float
    changePct: float
    asOf: str
    source: str
    delayed: bool


class TxnOut(BaseModel):
    key: str
    ticker: str
    date: str
    name: str
    role: str | None
    action: str
    typeLabel: str
    shares: float
    value: float | None
    starred: bool
    is10b5_1: bool = False


class FreshnessOut(BaseModel):
    asOf: str | None
    stale: bool


class DashboardOut(BaseModel):
    signals: list[SignalOut]
    quotes: dict[str, QuoteOut]
    tape: list[TxnOut]
    lookbackMonths: int
    latestFilingDate: str | None
    generatedAt: str
    freshness: dict[str, FreshnessOut]


class HistoryPoint(BaseModel):
    date: str
    close: float


class HolderOut(BaseModel):
    rank: int
    institution: str
    shares: float
    value: float
    qoqChangePct: float | None
    reportPeriod: str


class RefreshOut(BaseModel):
    jobId: str
    status: str


class WatchlistOut(BaseModel):
    tickers: list[str]


class WatchlistIn(BaseModel):
    tickers: list[str]
