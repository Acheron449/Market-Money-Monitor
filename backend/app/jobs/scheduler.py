"""APScheduler wiring for the cadences in SRS 5.4 (AUT-01)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from app.core.calendar import ET, is_evening, is_market_open, is_trading_day
from app.jobs.runner import run_bars, run_form4, run_holders, run_quotes, run_ticker_map

LOGGER = logging.getLogger(__name__)


async def _quotes_market(app: FastAPI) -> None:
    if is_market_open(datetime.now(UTC)):
        await run_quotes(app)


async def _quotes_offhours(app: FastAPI) -> None:
    now = datetime.now(UTC)
    if is_trading_day(now.date()) and not is_market_open(now):
        await run_quotes(app)


async def _form4_due(app: FastAPI) -> None:
    now = datetime.now(UTC)
    local = now.astimezone(ET)
    if is_market_open(now) or is_evening(now) or local.minute < 5:
        await run_form4(app)


def build_scheduler(app: FastAPI) -> AsyncIOScheduler:
    cadence = app.state.config.cadences
    scheduler = AsyncIOScheduler(timezone=UTC)
    scheduler.add_job(
        _quotes_market,
        "interval",
        seconds=cadence.quotes_market_seconds,
        args=[app],
        id="quotes_market",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _quotes_offhours,
        "interval",
        seconds=cadence.quotes_offhours_seconds,
        args=[app],
        id="quotes_offhours",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _form4_due,
        "interval",
        seconds=cadence.form4_seconds,
        args=[app],
        id="form4",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_bars,
        CronTrigger(hour=16, minute=30, timezone=ET),
        args=[app],
        id="bars",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_holders,
        CronTrigger(hour=6, minute=0, timezone=ET),
        args=[app],
        id="holders",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_ticker_map,
        CronTrigger(day_of_week="mon", hour=5, minute=0, timezone=ET),
        args=[app],
        id="ticker_map",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
