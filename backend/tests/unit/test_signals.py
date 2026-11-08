"""SIG-05 to SIG-10 unit tests (AC-08)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.services.signals import (
    cluster_buy_dates,
    compute_signal,
    emphasis,
    in_window,
    shift_months,
)

AS_OF = date(2026, 11, 8)


@dataclass
class Row:
    txn_date: date
    action: str
    value: Decimal | None
    role: str = "Other"
    insider_name: str = ""
    insider_cik: str | None = None
    is_10b5_1: bool = False


def test_net_value_is_buys_minus_sells() -> None:
    rows = [
        Row(date(2026, 10, 1), "buy", Decimal("3000000"), "CEO"),
        Row(date(2026, 10, 2), "sell", Decimal("1000000"), "CFO"),
        Row(date(2026, 10, 3), "buy", Decimal("250000"), "Director"),
    ]
    result = compute_signal(rows, as_of=AS_OF, lookback_months=6)
    assert result.buy_value == Decimal("3250000")
    assert result.sell_value == Decimal("1000000")
    assert result.net_value == Decimal("2250000")
    assert result.txn_count == 3
    assert result.starred_count == 1
    assert result.cluster_buy is False


def test_awards_gifts_and_withholdings_are_excluded() -> None:
    rows = [
        Row(date(2026, 10, 1), "other", Decimal("9999999"), "CEO"),
        Row(date(2026, 10, 2), "buy", None, "CEO"),
    ]
    result = compute_signal(rows, as_of=AS_OF, lookback_months=6)
    assert result.net_value == Decimal("0")
    assert result.txn_count == 1
    assert result.starred_count == 1


def test_rows_outside_window_are_excluded() -> None:
    rows = [Row(date(2026, 1, 1), "buy", Decimal("5000000"), "CEO")]
    assert compute_signal(rows, as_of=AS_OF, lookback_months=6).net_value == 0
    assert compute_signal(rows, as_of=AS_OF, lookback_months=12).net_value == Decimal("5000000")


def test_sell_heavy_net_is_negative_and_emphasis_is_sign_aware() -> None:
    rows = [
        Row(date(2026, 9, 1), "buy", Decimal("1000000"), "CEO"),
        Row(date(2026, 9, 2), "sell", Decimal("12000000"), "Director"),
    ]
    result = compute_signal(rows, as_of=AS_OF, lookback_months=6)
    assert result.net_value == Decimal("-11000000")
    assert emphasis(result.net_value) == "strong"
    assert emphasis(Decimal("-6000000")) == "moderate"
    assert emphasis(Decimal("5000")) == "neutral"


def test_shift_months_clamps_to_month_end() -> None:
    assert shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert shift_months(date(2026, 1, 31), -1) == date(2025, 12, 31)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 5, 8), True),
        (date(2026, 5, 1), False),
        (date(2026, 12, 8), False),
    ],
)
def test_window_boundaries(day: date, expected: bool) -> None:
    assert in_window(day, date(2026, 11, 8), 6) is expected


def test_cluster_buy_requires_three_distinct_insiders_in_fourteen_days() -> None:
    rows = [
        Row(date(2026, 10, 1), "buy", Decimal("1"), "CEO", insider_name="ALPHA"),
        Row(date(2026, 10, 5), "sell", Decimal("1"), "CFO", insider_name="SELLER"),
        Row(date(2026, 10, 10), "buy", Decimal("1"), "Director", insider_name="BETA"),
        Row(date(2026, 10, 14), "buy", Decimal("1"), "Other", insider_name="GAMMA"),
    ]
    assert cluster_buy_dates(rows, as_of=AS_OF) is True
    assert cluster_buy_dates([rows[0], rows[2], rows[3]], as_of=AS_OF) is True
    assert cluster_buy_dates(rows[:3], as_of=AS_OF) is False

    repeated = [
        Row(date(2026, 10, 1), "buy", Decimal("1"), "CEO", insider_name="ALPHA"),
        Row(date(2026, 10, 5), "buy", Decimal("1"), "CEO", insider_name="ALPHA"),
        Row(date(2026, 10, 10), "buy", Decimal("1"), "CEO", insider_name="ALPHA"),
        Row(date(2026, 10, 12), "buy", Decimal("1"), "Director", insider_name="BETA"),
    ]
    assert cluster_buy_dates(repeated, as_of=AS_OF) is False

    spread = [
        Row(date(2026, 9, 1), "buy", Decimal("1"), "CEO", insider_name="ALPHA"),
        Row(date(2026, 9, 20), "buy", Decimal("1"), "CFO", insider_name="BETA"),
        Row(date(2026, 10, 10), "buy", Decimal("1"), "Director", insider_name="GAMMA"),
    ]
    assert cluster_buy_dates(spread, as_of=AS_OF) is False


def test_compute_signal_reports_cluster_buy() -> None:
    rows = [
        Row(date(2026, 10, 1), "buy", Decimal("100"), "CEO", insider_name="ALPHA"),
        Row(date(2026, 10, 2), "buy", Decimal("100"), "CFO", insider_name="BETA"),
        Row(date(2026, 10, 3), "buy", Decimal("100"), "Director", insider_name="GAMMA"),
    ]
    assert compute_signal(rows, as_of=AS_OF, lookback_months=6).cluster_buy is True


def test_10b5_1_sales_can_be_excluded_from_net() -> None:
    rows = [
        Row(date(2026, 10, 1), "buy", Decimal("1000000"), "CEO", insider_name="ALPHA"),
        Row(
            date(2026, 10, 2),
            "sell",
            Decimal("1000000"),
            "CFO",
            insider_name="BETA",
            is_10b5_1=True,
        ),
    ]
    included = compute_signal(rows, as_of=AS_OF, lookback_months=6)
    assert included.net_value == Decimal("0")
    assert included.sell_value == Decimal("1000000")
    assert included.txn_count == 2

    excluded = compute_signal(rows, as_of=AS_OF, lookback_months=6, exclude_10b5_1=True)
    assert excluded.net_value == Decimal("1000000")
    assert excluded.sell_value == Decimal("0")
    assert excluded.txn_count == 2
