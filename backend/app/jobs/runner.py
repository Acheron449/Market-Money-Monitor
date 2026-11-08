"""Job bodies. Every job is idempotent and takes the DB lock (AUT-06)."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import FastAPI

from app.core.errors import ProviderError
from app.providers.registry import ProviderRegistry
from app.services.alerts import emit_ingest_alerts
from app.services.ingest import (
    active_tickers,
    bars_gap_start,
    ingest_bars,
    ingest_holders,
    ingest_insider_rows,
    ingest_quotes,
    latest_net_values,
    recompute_signals,
    resolve_ciks,
    signals_for,
)
from app.services.signals import shift_months

LOGGER = logging.getLogger(__name__)
TIMEOUTS = {"quotes": 120, "form4": 900, "bars": 300, "holders": 300, "ticker_map": 120}


def _registry(app: FastAPI) -> ProviderRegistry:
    registry: ProviderRegistry = app.state.registry
    return registry


async def run_quotes(app: FastAPI) -> None:
    async with app.state.db.session() as session:
        tickers = await active_tickers(session)
        from app.jobs.lock import acquire, release

        if not await acquire(session, "quotes", ttl_seconds=TIMEOUTS["quotes"]):
            return
        try:
            await ingest_quotes(session, _registry(app), [t.symbol for t in tickers])
        except ProviderError as exc:
            LOGGER.warning("quote ingest failed", extra={"job": "quotes", "error": str(exc)})
        finally:
            await release(session, "quotes")


async def run_form4(app: FastAPI) -> None:
    from app.jobs.lock import acquire, release

    async with app.state.db.session() as session:
        if not await acquire(session, "form4", ttl_seconds=TIMEOUTS["form4"]):
            return
        try:
            tickers = await active_tickers(session)
            directory = _registry(app).directory
            if directory is not None and any(t.cik is None for t in tickers):
                try:
                    await resolve_ciks(session, directory)
                except ProviderError as exc:
                    LOGGER.warning(
                        "CIK resolution failed",
                        extra={"job": "form4", "error": str(exc)},
                    )
                tickers = await active_tickers(session)

            today = date.today()
            symbols = [ticker.symbol for ticker in tickers]
            since = shift_months(today, -6)
            previous_net = await latest_net_values(session, app.state.config.lookback_months)
            new_rows = await ingest_insider_rows(session, _registry(app), tickers, since)
            current = await signals_for(
                session,
                symbols,
                today,
                app.state.config.lookback_months,
            )
            await recompute_signals(
                session,
                symbols,
                today,
                app.state.config.lookback_months,
            )
            await emit_ingest_alerts(
                session,
                app.state.settings,
                new_rows=new_rows,
                previous_net=previous_net,
                current=current,
                as_of=today,
            )
        finally:
            await release(session, "form4")


async def run_bars(app: FastAPI) -> None:
    from app.jobs.lock import acquire, release

    async with app.state.db.session() as session:
        if not await acquire(session, "bars", ttl_seconds=TIMEOUTS["bars"]):
            return
        try:
            today = date.today()
            for ticker in await active_tickers(session):
                start = await bars_gap_start(session, ticker.symbol, today)
                if start > today:
                    continue
                try:
                    await ingest_bars(session, _registry(app), ticker.symbol, start, today)
                except ProviderError as exc:
                    LOGGER.warning(
                        "bar ingest failed",
                        extra={"job": "bars", "symbol": ticker.symbol, "error": str(exc)},
                    )
        finally:
            await release(session, "bars")


async def run_holders(app: FastAPI) -> None:
    from app.jobs.lock import acquire, release

    async with app.state.db.session() as session:
        if not await acquire(session, "holders", ttl_seconds=TIMEOUTS["holders"]):
            return
        try:
            for ticker in await active_tickers(session):
                try:
                    await ingest_holders(session, _registry(app), ticker.symbol)
                except ProviderError as exc:
                    LOGGER.warning(
                        "holder ingest failed",
                        extra={"job": "holders", "symbol": ticker.symbol, "error": str(exc)},
                    )
        finally:
            await release(session, "holders")


async def run_ticker_map(app: FastAPI) -> None:
    from app.jobs.lock import acquire, release

    async with app.state.db.session() as session:
        if not await acquire(session, "ticker_map", ttl_seconds=TIMEOUTS["ticker_map"]):
            return
        try:
            directory = _registry(app).directory
            if directory is not None:
                await resolve_ciks(session, directory)
        except ProviderError as exc:
            LOGGER.warning("ticker map failed", extra={"job": "ticker_map", "error": str(exc)})
        finally:
            await release(session, "ticker_map")


async def run_full_refresh(app: FastAPI) -> None:
    """Manual refresh (AUT-04): run every ingest in order, never raise to the caller."""

    for job in (run_quotes, run_form4, run_bars, run_holders):
        try:
            await job(app)
        except Exception:
            LOGGER.exception("refresh step failed", extra={"job": job.__name__})
