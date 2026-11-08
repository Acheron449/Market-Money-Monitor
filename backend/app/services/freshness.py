"""Per-source freshness metadata and stale flags (UI-11, AUT-05)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import RuntimeConfig, Settings
from app.core.calendar import is_market_open, is_trading_day
from app.db.models import IngestRun, InsiderTxn, PriceBar, Quote


@dataclass(frozen=True, slots=True)
class SourceFreshness:
    as_of: datetime | None
    stale: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "asOf": self.as_of.isoformat() if self.as_of else None,
            "stale": self.stale,
        }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _last_success(session: AsyncSession, job: str) -> datetime | None:
    return _aware(
        await session.scalar(
            select(func.max(IngestRun.finished_at)).where(
                IngestRun.job == job, IngestRun.status == "ok"
            )
        )
    )


async def build_freshness(
    session: AsyncSession,
    settings: Settings,
    config: RuntimeConfig,
    *,
    now: datetime | None = None,
) -> dict[str, SourceFreshness]:
    moment = now or datetime.now(UTC)
    cadence = config.cadences

    quote_as_of = _aware(await session.scalar(select(func.max(Quote.as_of))))
    quote_window = (
        settings.quote_stale_seconds
        if is_market_open(moment)
        else cadence.quotes_offhours_seconds * 2
    )
    quotes = SourceFreshness(
        as_of=quote_as_of,
        stale=quote_as_of is None or (moment - quote_as_of) > timedelta(seconds=quote_window),
    )

    filing_as_of = _aware(await session.scalar(select(func.max(InsiderTxn.created_at))))
    filings = SourceFreshness(
        as_of=filing_as_of,
        stale=filing_as_of is None
        or (moment - filing_as_of) > timedelta(seconds=cadence.form4_seconds * 2),
    )

    last_bar = await session.scalar(select(func.max(PriceBar.date)))
    today = moment.date()
    expected = today if is_trading_day(today) else today - timedelta(days=1)
    while not is_trading_day(expected):
        expected -= timedelta(days=1)
    bars = SourceFreshness(
        as_of=datetime.combine(last_bar, datetime.min.time(), tzinfo=UTC) if last_bar else None,
        stale=last_bar is None or last_bar < expected,
    )

    holder_as_of = await _last_success(session, "holders")
    holders = SourceFreshness(
        as_of=holder_as_of,
        stale=holder_as_of is None or (moment - holder_as_of) > timedelta(days=2),
    )

    return {"quotes": quotes, "filings": filings, "bars": bars, "holders": holders}


def latest_filing_date(rows: list[InsiderTxn]) -> date | None:
    return max((row.filing_date for row in rows), default=None)
