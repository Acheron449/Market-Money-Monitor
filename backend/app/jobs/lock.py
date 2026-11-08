"""Single-run job lock shared across restarts and replicas (AUT-06)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobLock


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def acquire(session: AsyncSession, name: str, *, ttl_seconds: int) -> bool:
    now = datetime.now(UTC)
    row = await session.get(JobLock, name)
    if row is not None and _aware(row.expires_at) > now:
        return False
    owner = f"{os.getpid()}-{uuid.uuid4().hex[:6]}"
    if row is None:
        session.add(
            JobLock(
                name=name,
                owner=owner,
                acquired_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
        )
    else:
        row.owner = owner
        row.acquired_at = now
        row.expires_at = now + timedelta(seconds=ttl_seconds)
    await session.commit()
    return True


async def release(session: AsyncSession, name: str) -> None:
    row = await session.get(JobLock, name)
    if row is not None:
        await session.delete(row)
        await session.commit()
