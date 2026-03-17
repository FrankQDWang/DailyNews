"""add ingest batch run snapshots

Revision ID: 0006_ingest_batch_runs
Revises: 0005_fetch_state_and_llm_usage
Create Date: 2026-03-17 20:50:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_ingest_batch_runs"
down_revision = "0005_fetch_state_and_llm_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "ingest_batch_runs" not in existing_tables:
        op.create_table(
            "ingest_batch_runs",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("scanned_count", sa.Integer(), nullable=False),
            sa.Column("actionable_count", sa.Integer(), nullable=False),
            sa.Column("marked_read_count", sa.Integer(), nullable=False),
            sa.Column("skipped_terminal_count", sa.Integer(), nullable=False),
            sa.Column("skipped_cooldown_count", sa.Integer(), nullable=False),
            sa.Column("skipped_blocked_count", sa.Integer(), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("ingest_batch_runs")}
    if "ix_ingest_batch_runs_finished_at" not in existing_indexes:
        op.create_index(
            "ix_ingest_batch_runs_finished_at",
            "ingest_batch_runs",
            [sa.text("finished_at DESC")],
            unique=False,
            postgresql_using="btree",
        )


def downgrade() -> None:
    op.drop_index("ix_ingest_batch_runs_finished_at", table_name="ingest_batch_runs", if_exists=True)
    op.drop_table("ingest_batch_runs", if_exists=True)
