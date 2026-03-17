"""add entry quarantine state

Revision ID: 0003_entry_quarantine
Revises: 0002_processed_telegram_updates
Create Date: 2026-03-17 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_entry_quarantine"
down_revision = "0002_processed_telegram_updates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute("ALTER TYPE entry_status ADD VALUE IF NOT EXISTS 'quarantined'")

    existing_columns = {column["name"] for column in inspector.get_columns("entries")}
    if "quarantine_reason" not in existing_columns:
        op.add_column("entries", sa.Column("quarantine_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("entries")}
    if "quarantine_reason" in existing_columns:
        op.drop_column("entries", "quarantine_reason")
