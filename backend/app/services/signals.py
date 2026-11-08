"""Dollar-weighted signals over a lookback window (SIG-05 to SIG-10)."""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

ZERO = Decimal("0")


class TxnLike(Protocol):
    txn_date: date
    action: str
    value: Decimal | None
    role: str
    insider_cik: str | None
    insider_name: str
    is_10b5_1: bool


@dataclass(frozen=True, slots=True)
class SignalResult:
    net_value: Decimal
    buy_value: Decimal
    sell_value: Decimal
    txn_count: int
    starred_count: int
    cluster_buy: bool = False


def shift_months(day: date, months: int) -> date:
    """Calendar-month arithmetic clamping the day: 31 Jan minus one month is 28/29 Feb."""

    total = day.year * 12 + (day.month - 1) + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def in_window(day: date, as_of: date, lookback_months: int) -> bool:
    start = shift_months(as_of, -lookback_months)
    return start <= day <= as_of


def compute_signal(
    rows: Iterable[TxnLike],
    *,
    as_of: date,
    lookback_months: int,
    exclude_10b5_1: bool = False,
) -> SignalResult:
    """Only open-market P/S rows inside the window count; everything else is ignored.

    SIG-10's opt-in toggle removes 10b5-1 sales from net, sell value and txn count.
    The tape still shows the rows and their badge.
    """

    windowed = [row for row in rows if in_window(row.txn_date, as_of, lookback_months)]
    buy = ZERO
    sell = ZERO
    count = 0
    starred = 0
    for row in windowed:
        if row.action not in {"buy", "sell"}:
            continue
        if exclude_10b5_1 and row.action == "sell" and row.is_10b5_1:
            # SIG-10 excludes the sale from net, while SIG-05 still counts the row.
            count += 1
            continue
        amount = row.value or ZERO
        if row.action == "buy":
            buy += amount
        else:
            sell += amount
        count += 1
        if row.action == "buy" and row.role in {"CEO", "CFO"}:
            starred += 1
    return SignalResult(
        net_value=buy - sell,
        buy_value=buy,
        sell_value=sell,
        txn_count=count,
        starred_count=starred,
        cluster_buy=cluster_buy_dates(windowed, as_of=as_of),
    )


def emphasis(net_value: Decimal) -> str:
    """Sign-aware tile emphasis (SIG-07): strong ≥ $10M, moderate ≥ $1M."""

    magnitude = abs(net_value)
    if magnitude >= Decimal("10000000"):
        return "strong"
    if magnitude >= Decimal("1000000"):
        return "moderate"
    return "neutral"


def _insider_key(row: TxnLike) -> str:
    if row.insider_cik:
        return f"cik:{row.insider_cik}"
    return f"name:{row.insider_name.strip().upper()}"


def cluster_buy_dates(rows: Sequence[TxnLike], *, as_of: date, window_days: int = 14) -> bool:
    """SIG-09: three or more distinct insiders buying inside a rolling 14-day window."""

    buys = sorted(
        (row.txn_date, _insider_key(row))
        for row in rows
        if row.action == "buy" and row.txn_date <= as_of
    )
    for index, (start, _) in enumerate(buys):
        insiders = {key for day, key in buys[index:] if (day - start).days <= window_days}
        if len(insiders) >= 3:
            return True
    return False
