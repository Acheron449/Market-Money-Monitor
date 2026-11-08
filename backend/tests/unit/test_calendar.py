"""Market calendar: holidays and early closes (AUT-01)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.core.calendar import is_market_open, is_trading_day, market_close_utc, market_open_utc


def test_thanksgiving_is_closed() -> None:
    assert is_trading_day(date(2026, 11, 26)) is False
    assert market_open_utc(date(2026, 11, 26)) is None


def test_day_after_thanksgiving_is_an_early_close() -> None:
    assert is_trading_day(date(2026, 11, 27)) is True
    assert market_close_utc(date(2026, 11, 27)) == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)


def test_christmas_and_new_year_are_closed() -> None:
    assert is_trading_day(date(2026, 12, 25)) is False
    assert is_trading_day(date(2027, 1, 1)) is False


def test_regular_session_window() -> None:
    assert market_open_utc(date(2026, 11, 10)) == datetime(2026, 11, 10, 14, 30, tzinfo=UTC)
    assert market_close_utc(date(2026, 11, 10)) == datetime(2026, 11, 10, 21, 0, tzinfo=UTC)


def test_market_open_uses_new_york_time() -> None:
    assert is_market_open(datetime(2026, 11, 10, 15, 0, tzinfo=UTC)) is True
    assert is_market_open(datetime(2026, 11, 10, 13, 0, tzinfo=UTC)) is False
    assert is_market_open(datetime(2026, 11, 7, 15, 0, tzinfo=UTC)) is False
