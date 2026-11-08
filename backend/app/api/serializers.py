"""Shared API serializers for rows used by both the dashboard and the stream."""

from __future__ import annotations

from app.api.schemas import TxnOut
from app.db.models import InsiderTxn
from app.services.classification import classify, is_starred


def txn_out(row: InsiderTxn) -> TxnOut:
    return TxnOut(
        key=f"{row.accession_no}:{row.line_no}",
        ticker=row.symbol,
        date=row.txn_date.isoformat(),
        name=row.insider_name,
        role=row.role,
        action=row.action,
        typeLabel=classify(row.txn_code).type_label,
        shares=float(row.shares),
        value=float(row.value) if row.value is not None else None,
        starred=is_starred(row.action, row.role),
        is10b5_1=row.is_10b5_1,
    )
