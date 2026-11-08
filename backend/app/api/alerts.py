"""GET /api/alerts: recent ADM-03 alert history."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas import AlertOut
from app.db.models import AlertEvent

router = APIRouter()


@router.get("/api/alerts", response_model=list[AlertOut])
async def alerts(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[AlertOut]:
    rows = await session.scalars(
        select(AlertEvent).order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc()).limit(limit)
    )
    return [
        AlertOut(
            id=row.id,
            kind=row.kind,
            symbol=row.symbol,
            title=row.title,
            body=row.body,
            createdAt=_iso(row.created_at),
            channels=[channel for channel in row.channels.split(",") if channel],
            status=row.status,
        )
        for row in rows
    ]


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()
