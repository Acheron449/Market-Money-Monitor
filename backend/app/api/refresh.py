"""POST /api/refresh: enqueue an immediate run, throttled to one per 30 s (AUT-04)."""

from __future__ import annotations

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_settings, require_admin_if_remote
from app.api.schemas import RefreshOut
from app.config import Settings
from app.jobs.runner import run_full_refresh

router = APIRouter()


@router.post("/api/refresh", status_code=202, response_model=RefreshOut)
async def refresh(request: Request, settings: Settings = Depends(get_settings)) -> RefreshOut:
    require_admin_if_remote(request, settings)

    now = time.monotonic()
    last = float(getattr(request.app.state, "last_refresh", 0.0))
    if now - last < settings.refresh_throttle_seconds:
        from app.api.errors import ApiError

        wait = settings.refresh_throttle_seconds - int(now - last)
        raise ApiError(
            429,
            "throttled",
            f"Refresh is limited to once per {settings.refresh_throttle_seconds} s; "
            f"retry in {wait} s",
        )
    request.app.state.last_refresh = now

    job_id = uuid.uuid4().hex[:12]
    task = asyncio.create_task(run_full_refresh(request.app))
    tasks: set[asyncio.Task[None]] = getattr(request.app.state, "tasks", set())
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    request.app.state.tasks = tasks
    return RefreshOut(jobId=job_id, status="accepted")
