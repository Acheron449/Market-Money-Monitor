"""SEC bulk cross-check discrepancies

Revision ID: c3f6a9d2e4b1
Revises: 8f3b2a1c4d5e
Create Date: 2026-11-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f6a9d2e4b1"
down_revision: str | Sequence[str] | None = "8f3b2a1c4d5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "cross_check_discrepancy",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("accession_no", sa.String(length=32), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=16), nullable=False),
        sa.Column("primary_value", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("secondary_value", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("difference_pct", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ingest_run.id"]),
        sa.ForeignKeyConstraint(["symbol"], ["ticker.symbol"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cross_check_discrepancy_run_id"), "cross_check_discrepancy", ["run_id"]
    )
    op.create_index(
        op.f("ix_cross_check_discrepancy_checked_at"),
        "cross_check_discrepancy",
        ["checked_at"],
    )
    op.create_index(
        op.f("ix_cross_check_discrepancy_symbol"), "cross_check_discrepancy", ["symbol"]
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_cross_check_discrepancy_symbol"), table_name="cross_check_discrepancy")
    op.drop_index(
        op.f("ix_cross_check_discrepancy_checked_at"), table_name="cross_check_discrepancy"
    )
    op.drop_index(op.f("ix_cross_check_discrepancy_run_id"), table_name="cross_check_discrepancy")
    op.drop_table("cross_check_discrepancy")
