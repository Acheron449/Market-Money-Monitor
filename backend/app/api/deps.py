"""API dependencies: DB sessions, configuration and the admin token check (ADM-02)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.config import RuntimeConfig, Settings
from app.db.session import Database

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.db
    async with database.session() as session:
        yield session


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_config(request: Request) -> RuntimeConfig:
    config: RuntimeConfig = request.app.state.config
    return config


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def require_admin(request: Request, settings: Settings) -> None:
    token = _bearer(request)
    if not settings.admin_token or token != settings.admin_token:
        raise ApiError(401, "unauthorized", "A valid admin bearer token is required")


def require_admin_if_remote(request: Request, settings: Settings) -> None:
    host = request.client.host if request.client else ""
    if host in LOOPBACK_HOSTS:
        return
    require_admin(request, settings)
