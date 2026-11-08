"""EDGAR reconciliation mismatches

Revision ID: d7b2e5f8a1c9
Revises: c3f6a9d2e4b1
Create Date: 2026-11-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7b2e5f8a1c9"
down_revision: str | Sequence[str] | None = "c3f6a9d2e4b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "reconciliation_mismatch",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("accession_no", sa.String(length=32), nullable=False),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("expected", sa.Text(), nullable=False),
        sa.Column("actual", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ingest_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reconciliation_mismatch_run_id"), "reconciliation_mismatch", ["run_id"]
    )
    op.create_index(
        op.f("ix_reconciliation_mismatch_checked_at"),
        "reconciliation_mismatch",
        ["checked_at"],
    )
    op.create_index(
        op.f("ix_reconciliation_mismatch_symbol"), "reconciliation_mismatch", ["symbol"]
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_reconciliation_mismatch_symbol"), table_name="reconciliation_mismatch")
    op.drop_index(
        op.f("ix_reconciliation_mismatch_checked_at"), table_name="reconciliation_mismatch"
    )
    op.drop_index(op.f("ix_reconciliation_mismatch_run_id"), table_name="reconciliation_mismatch")
    op.drop_table("reconciliation_mismatch")
