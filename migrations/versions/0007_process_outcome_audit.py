"""add process outcome audit fields

Revision ID: 0007_process_outcome_audit
Revises: 0006_ingest_batch_runs
Create Date: 2026-03-17 21:40:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_process_outcome_audit"
down_revision = "0006_ingest_batch_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("entries")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("entries")}

    if "last_process_outcome" not in existing_columns:
        op.add_column("entries", sa.Column("last_process_outcome", sa.Text(), nullable=True))
    if "last_process_reason" not in existing_columns:
        op.add_column("entries", sa.Column("last_process_reason", sa.Text(), nullable=True))
    if "last_processed_at" not in existing_columns:
        op.add_column("entries", sa.Column("last_processed_at", sa.DateTime(timezone=True), nullable=True))

    if "ix_entries_last_process_outcome" not in existing_indexes:
        op.create_index(
            "ix_entries_last_process_outcome",
            "entries",
            ["last_process_outcome"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_entries_last_process_outcome", table_name="entries", if_exists=True)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("entries")}
    for column_name in ("last_processed_at", "last_process_reason", "last_process_outcome"):
        if column_name in existing_columns:
            op.drop_column("entries", column_name)
