"""NYSE calendar: sessions, holidays and early closes (AUT-01)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

ET = ZoneInfo("America/New_York")


@lru_cache
def _calendar() -> xcals.ExchangeCalendar:
    return xcals.get_calendar("XNYS", start="2015-01-01", end="2035-12-31")


def is_trading_day(day: date) -> bool:
    return bool(_calendar().is_session(pd.Timestamp(day)))


def market_open_utc(day: date) -> datetime | None:
    """Regular session open in UTC, or None on a holiday/weekend."""

    if not is_trading_day(day):
        return None
    stamp = _calendar().session_open(pd.Timestamp(day))
    return stamp.to_pydatetime().astimezone(UTC)


def market_close_utc(day: date) -> datetime | None:
    """Regular session close in UTC; honours the 13:00 early closes."""

    if not is_trading_day(day):
        return None
    stamp = _calendar().session_close(pd.Timestamp(day))
    return stamp.to_pydatetime().astimezone(UTC)


def is_market_open(now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("is_market_open requires an aware datetime")
    now_utc = now.astimezone(UTC)
    today = now_utc.astimezone(ET).date()
    opening = market_open_utc(today)
    closing = market_close_utc(today)
    if opening is None or closing is None:
        return False
    return opening <= now_utc < closing


def is_evening(now: datetime) -> bool:
    """Weekday after the close and before 22:00 ET, when Form 4s cluster."""

    local = now.astimezone(ET)
    return local.weekday() < 5 and time(16, 0) <= local.time() < time(22, 0)
