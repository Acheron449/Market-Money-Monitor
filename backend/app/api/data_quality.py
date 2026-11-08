"""GET /api/data-quality: cross-check and SEC bulk-load status (ING-11, ING-12)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas import (
    BulkLoadSummaryOut,
    CrossCheckSummaryOut,
    DataQualityOut,
    DiscrepancyOut,
)
from app.db.models import CrossCheckDiscrepancy, IngestRun

router = APIRouter()


@router.get("/api/data-quality", response_model=DataQualityOut)
async def data_quality(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> DataQualityOut:
    cross_run = await _latest(session, "cross_check")
    insider_run = await _latest(session, "bulk_insider")
    bulk_run = await _latest(session, "bulk_13f")
    count = 0
    if cross_run is not None:
        count = int(
            await session.scalar(
                select(func.count())
                .select_from(CrossCheckDiscrepancy)
                .where(CrossCheckDiscrepancy.run_id == cross_run.id)
            )
            or 0
        )
    rows = list(
        await session.scalars(
            select(CrossCheckDiscrepancy)
            .order_by(CrossCheckDiscrepancy.checked_at.desc(), CrossCheckDiscrepancy.id.desc())
            .limit(limit)
        )
    )
    return DataQualityOut(
        crossCheck=CrossCheckSummaryOut(
            at=_run_at(cross_run),
            provider=cross_run.provider if cross_run is not None else None,
            checked=cross_run.rows if cross_run is not None else 0,
            discrepancies=count,
            status=cross_run.status if cross_run is not None else "never",
        ),
        bulkInsider=_bulk(insider_run),
        bulk13f=_bulk(bulk_run),
        discrepancies=[
            DiscrepancyOut(
                id=row.id,
                checkedAt=_iso(row.checked_at),
                symbol=row.symbol,
                accessionNo=row.accession_no,
                lineNo=row.line_no,
                field=row.field,
                primaryValue=float(row.primary_value) if row.primary_value is not None else None,
                secondaryValue=(
                    float(row.secondary_value) if row.secondary_value is not None else None
                ),
                differencePct=float(row.difference_pct),
                provider=row.provider,
            )
            for row in rows
        ],
    )


async def _latest(session: AsyncSession, job: str) -> IngestRun | None:
    return await session.scalar(
        select(IngestRun)
        .where(IngestRun.job == job)
        .order_by(IngestRun.started_at.desc(), IngestRun.id.desc())
        .limit(1)
    )


def _bulk(run: IngestRun | None) -> BulkLoadSummaryOut:
    return BulkLoadSummaryOut(
        at=_run_at(run),
        rows=run.rows if run is not None else 0,
        status=run.status if run is not None else "never",
    )


def _run_at(run: IngestRun | None) -> str | None:
    if run is None:
        return None
    value = run.finished_at or run.started_at
    return _iso(value)


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()
