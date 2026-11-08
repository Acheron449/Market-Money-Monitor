"""Entities from SRS 6.1, plus the job lock used for single-run scheduling."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MONEY = Numeric(20, 4)
SHARES = Numeric(20, 4)
PERCENT = Numeric(12, 4)


class Ticker(Base):
    __tablename__ = "ticker"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    cik: Mapped[str | None] = mapped_column(String(10), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    exchange: Mapped[str | None] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Quote(Base):
    __tablename__ = "quote"

    symbol: Mapped[str] = mapped_column(ForeignKey("ticker.symbol"), primary_key=True)
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    change_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    delayed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PriceBar(Base):
    __tablename__ = "price_bar"

    symbol: Mapped[str] = mapped_column(ForeignKey("ticker.symbol"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal | None] = mapped_column(MONEY)
    high: Mapped[Decimal | None] = mapped_column(MONEY)
    low: Mapped[Decimal | None] = mapped_column(MONEY)
    close: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class InsiderTxn(Base):
    __tablename__ = "insider_txn"

    accession_no: Mapped[str] = mapped_column(String(32), primary_key=True)
    line_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("ticker.symbol"), index=True, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    txn_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    insider_name: Mapped[str] = mapped_column(String(200), nullable=False)
    insider_cik: Mapped[str | None] = mapped_column(String(20))
    officer_title: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    txn_code: Mapped[str] = mapped_column(String(4), nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    shares: Mapped[Decimal] = mapped_column(SHARES, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    value: Mapped[Decimal | None] = mapped_column(MONEY)
    shares_after: Mapped[Decimal | None] = mapped_column(SHARES)
    is_10b5_1: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Holder(Base):
    __tablename__ = "holder"

    symbol: Mapped[str] = mapped_column(ForeignKey("ticker.symbol"), primary_key=True)
    report_period: Mapped[date] = mapped_column(Date, primary_key=True)
    institution_cik: Mapped[str] = mapped_column(String(20), primary_key=True)
    institution: Mapped[str] = mapped_column(String(200), nullable=False)
    shares: Mapped[Decimal] = mapped_column(SHARES, nullable=False)
    value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    prev_shares: Mapped[Decimal | None] = mapped_column(SHARES)
    qoq_change_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class SignalSnapshot(Base):
    __tablename__ = "signal_snapshot"

    symbol: Mapped[str] = mapped_column(ForeignKey("ticker.symbol"), primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    lookback_months: Mapped[int] = mapped_column(Integer, primary_key=True)
    net_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    buy_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    sell_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    txn_count: Mapped[int] = mapped_column(Integer, nullable=False)
    starred_count: Mapped[int] = mapped_column(Integer, nullable=False)


class AlertEvent(Base):
    __tablename__ = "alert_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(ForeignKey("ticker.symbol"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    channels: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="recorded", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IngestRun(Base):
    __tablename__ = "ingest_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class JobLock(Base):
    __tablename__ = "job_lock"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
