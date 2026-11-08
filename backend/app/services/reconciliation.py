"""AC-01: reconcile parsed Form 4 rows against a frozen EDGAR-shaped snapshot."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ParseError
from app.db.models import ReconciliationMismatch
from app.parsers.form4 import parse_form4
from app.services.ingest import track_run

LOGGER = logging.getLogger(__name__)
JOB = "edgar_reconciliation"
PROVIDER = "sec_edgar_snapshot"


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    checked: int
    mismatches: int
    provider: str


@dataclass(frozen=True, slots=True)
class _Case:
    symbol: str
    accession_no: str
    filing_date: date
    document: str
    shares: Decimal
    price: Decimal | None
    txn_code: str
    txn_date: date
    insider_name: str
    insider_cik: str


async def reconcile_edgar(session: AsyncSession, snapshot: Path) -> ReconciliationResult:
    """Parse every filing in a local EDGAR snapshot and compare five claimed fields."""

    cases = load_snapshot(snapshot)
    checked = 0
    mismatches: list[ReconciliationMismatch] = []
    checked_at = datetime.now(UTC)

    async with track_run(session, job=JOB, provider=PROVIDER) as run:
        for case in cases:
            checked += 1
            document = snapshot.parent / case.document
            try:
                parsed = parse_form4(
                    document.read_bytes(),
                    accession_no=case.accession_no,
                    filing_date=case.filing_date,
                    source=PROVIDER,
                    fallback_symbol=case.symbol,
                )
            except (OSError, ParseError) as exc:
                mismatches.append(
                    _mismatch(
                        run.id,
                        checked_at,
                        case,
                        "document",
                        "readable Form 4 XML",
                        str(exc),
                    )
                )
                continue

            if len(parsed.transactions) != 1:
                mismatches.append(
                    _mismatch(
                        run.id,
                        checked_at,
                        case,
                        "document",
                        "1 non-derivative transaction",
                        f"{len(parsed.transactions)} non-derivative transactions",
                    )
                )
                continue

            txn = parsed.transactions[0]
            for field, expected, actual in (
                ("shares", case.shares, txn.shares),
                ("price", case.price, txn.price),
                ("code", case.txn_code, txn.txn_code),
                ("date", case.txn_date, txn.txn_date),
                (
                    "owner",
                    f"{case.insider_name} ({case.insider_cik})",
                    f"{txn.insider_name} ({txn.insider_cik or '—'})",
                ),
            ):
                if expected != actual:
                    mismatches.append(
                        _mismatch(
                            run.id,
                            checked_at,
                            case,
                            field,
                            _display(expected),
                            _display(actual),
                        )
                    )

        for mismatch in mismatches:
            LOGGER.warning(
                "EDGAR reconciliation mismatch",
                extra={
                    "symbol": mismatch.symbol,
                    "accession": mismatch.accession_no,
                    "field": mismatch.field,
                    "expected": mismatch.expected,
                    "actual": mismatch.actual,
                },
            )
        session.add_all(mismatches)
        run.rows = checked
        if mismatches:
            run.status = "error"
            run.error = f"{len(mismatches)} mismatch(es) across {checked} filings"

    return ReconciliationResult(checked, len(mismatches), PROVIDER)


def load_snapshot(path: Path) -> list[_Case]:
    """Load and validate the local EDGAR snapshot manifest."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"snapshot not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"snapshot is not valid JSON: {path}") from exc
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"snapshot must contain a non-empty list: {path}")
    return [_case(item, index) for index, item in enumerate(raw)]


def _case(item: object, index: int) -> _Case:
    if not isinstance(item, dict):
        raise ValueError(f"snapshot case {index}: expected an object")

    def text(key: str) -> str:
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"snapshot case {index}: {key} must be a non-empty string")
        return value.strip()

    def day(key: str) -> date:
        try:
            return date.fromisoformat(text(key))
        except ValueError as exc:
            raise ValueError(f"snapshot case {index}: {key} must be an ISO date") from exc

    try:
        shares = Decimal(text("shares"))
    except InvalidOperation as exc:
        raise ValueError(f"snapshot case {index}: shares must be decimal") from exc

    raw_price = item.get("price")
    price: Decimal | None
    if raw_price is None or raw_price == "":
        price = None
    else:
        try:
            price = Decimal(str(raw_price))
        except InvalidOperation as exc:
            raise ValueError(f"snapshot case {index}: price must be decimal or null") from exc

    return _Case(
        symbol=text("symbol").upper(),
        accession_no=text("accession_no"),
        filing_date=day("filing_date"),
        document=text("document"),
        shares=shares,
        price=price,
        txn_code=text("txn_code").upper(),
        txn_date=day("txn_date"),
        insider_name=text("insider_name"),
        insider_cik=text("insider_cik"),
    )


def _mismatch(
    run_id: int | None,
    checked_at: datetime,
    case: _Case,
    field: str,
    expected: str,
    actual: str,
) -> ReconciliationMismatch:
    return ReconciliationMismatch(
        run_id=run_id,
        checked_at=checked_at,
        symbol=case.symbol,
        accession_no=case.accession_no,
        field=field,
        expected=expected,
        actual=actual,
    )


def _display(value: object) -> str:
    return "—" if value is None else str(value)
