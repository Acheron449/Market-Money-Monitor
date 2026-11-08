"""AC-01: offline EDGAR Form 4 reconciliation."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import IngestRun, ReconciliationMismatch
from app.services.reconciliation import load_snapshot, reconcile_edgar

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "reconciliation"
SNAPSHOT = FIXTURES / "edgar_snapshot.json"


def test_snapshot_contains_five_filings_for_each_watchlist_ticker() -> None:
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert len(rows) == 40
    assert Counter(row["symbol"] for row in rows) == {
        "NVDA": 5,
        "AAPL": 5,
        "TSLA": 5,
        "AMZN": 5,
        "META": 5,
        "AMD": 5,
        "PLTR": 5,
        "COIN": 5,
    }
    assert len(load_snapshot(SNAPSHOT)) == 40


async def test_reconciliation_passes_all_forty_filings(client: AsyncClient) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    async with app.state.db.session() as session:
        result = await reconcile_edgar(session, SNAPSHOT)

    assert result.checked == 40
    assert result.mismatches == 0
    assert result.provider == "sec_edgar_snapshot"

    async with app.state.db.session() as session:
        run = await session.scalar(select(IngestRun).where(IngestRun.job == "edgar_reconciliation"))
        mismatches = list(await session.scalars(select(ReconciliationMismatch)))

    assert run is not None
    assert run.status == "ok"
    assert run.rows == 40
    assert run.error is None
    assert mismatches == []

    body = (await client.get("/api/data-quality")).json()
    assert body["reconciliation"]["checked"] == 40
    assert body["reconciliation"]["mismatches"] == 0
    assert body["reconciliation"]["status"] == "ok"
    assert body["reconciliation"]["error"] is None


async def test_reconciliation_persists_mismatches_and_marks_the_run(
    client: AsyncClient, tmp_path: Path
) -> None:
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows[0]["shares"] = "9999"
    shutil.copytree(FIXTURES / "documents", tmp_path / "documents")
    snapshot = tmp_path / "edgar_snapshot.json"
    snapshot.write_text(json.dumps(rows), encoding="utf-8")

    app = client._transport.app  # type: ignore[attr-defined]
    async with app.state.db.session() as session:
        result = await reconcile_edgar(session, snapshot)

    assert result.checked == 40
    assert result.mismatches == 1

    async with app.state.db.session() as session:
        run = await session.scalar(select(IngestRun).where(IngestRun.job == "edgar_reconciliation"))
        mismatch = await session.scalar(select(ReconciliationMismatch))

    assert run is not None
    assert run.status == "error"
    assert run.error == "1 mismatch(es) across 40 filings"
    assert mismatch is not None
    assert mismatch.field == "shares"
    assert mismatch.expected == "9999"
    assert mismatch.actual == "1000"

    body = (await client.get("/api/data-quality")).json()
    assert body["reconciliation"]["checked"] == 40
    assert body["reconciliation"]["mismatches"] == 1
    assert body["reconciliation"]["status"] == "error"
    assert body["reconciliation"]["error"] == "1 mismatch(es) across 40 filings"


def test_snapshot_validation_rejects_missing_and_malformed_manifests(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="snapshot not found"):
        load_snapshot(tmp_path / "missing.json")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_snapshot(invalid)

    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty list"):
        load_snapshot(empty)

    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps([{"symbol": "NVDA"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="shares must be a non-empty string"):
        load_snapshot(incomplete)

    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    del rows[0]["accession_no"]
    missing_accession = tmp_path / "missing_accession.json"
    missing_accession.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError, match="accession_no"):
        load_snapshot(missing_accession)
