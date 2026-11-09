"""FastAPI app factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    alerts,
    dashboard,
    data_quality,
    errors,
    health,
    history,
    holders,
    refresh,
    stream,
    watchlist,
)
from app.config import Settings, get_settings, load_runtime_config, validate_settings
from app.core.errors import ProviderError
from app.core.logging import configure_logging
from app.db.session import Database
from app.jobs.runner import run_bars
from app.jobs.scheduler import build_scheduler
from app.providers.registry import build_registry
from app.services.ingest import active_tickers, resolve_ciks, seed_watchlist

LOGGER = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    validate_settings(resolved)
    configure_logging(resolved.log_level)
    config = load_runtime_config(resolved)

    app = FastAPI(
        title="Smart Money Monitor",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = resolved
    app.state.config = config
    app.state.db = Database(resolved.database_url)
    app.state.registry = build_registry(resolved, config)
    app.state.scheduler = None
    app.state.last_refresh = 0.0
    app.state.tasks = set()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.parsed_cors_origins,
        allow_methods=["GET", "PUT", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    for module in (
        alerts,
        dashboard,
        data_quality,
        history,
        holders,
        refresh,
        watchlist,
        health,
        stream,
    ):
        app.include_router(module.router)
    errors.register(app)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database: Database = application.state.db
        await database.create_all()
        async with database.session() as session:
            await seed_watchlist(session, application.state.config)
            tickers = await active_tickers(session)
            if resolved.scheduler_enabled and any(t.cik is None for t in tickers):
                try:
                    await resolve_ciks(session, application.state.registry.directory)
                except ProviderError as exc:
                    LOGGER.warning("startup CIK resolution failed: %s", exc)

        if resolved.scheduler_enabled:
            scheduler = build_scheduler(application)
            scheduler.start()
            application.state.scheduler = scheduler
            application.state.tasks.add(asyncio.create_task(run_bars(application)))

        yield

        if application.state.scheduler is not None:
            application.state.scheduler.shutdown(wait=False)
        for task in list(application.state.tasks):
            task.cancel()
        await application.state.registry.close()
        await database.dispose()

    app.router.lifespan_context = lifespan
    return app


app = create_app()
