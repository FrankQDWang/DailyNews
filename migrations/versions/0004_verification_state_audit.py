"""add verification state audit fields

Revision ID: 0004_verification_state_audit
Revises: 0003_entry_quarantine
Create Date: 2026-03-17 11:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_verification_state_audit"
down_revision = "0003_entry_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE verification_state AS ENUM (
                'not_required',
                'pending',
                'verified',
                'failed',
                'legacy_gap'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    existing_columns = {column["name"] for column in inspector.get_columns("entries")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("entries")}
    verification_state_enum = sa.Enum(
        "not_required",
        "pending",
        "verified",
        "failed",
        "legacy_gap",
        name="verification_state",
        create_type=False,
    )

    if "verification_state" not in existing_columns:
        op.add_column(
            "entries",
            sa.Column("verification_state", verification_state_enum, nullable=True),
        )
    if "verification_reason" not in existing_columns:
        op.add_column("entries", sa.Column("verification_reason", sa.Text(), nullable=True))
    if "verified_at" not in existing_columns:
        op.add_column("entries", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))

    if "ix_entries_verification_state" not in existing_indexes:
        op.create_index(
            "ix_entries_verification_state",
            "entries",
            ["verification_state"],
            unique=False,
        )

    op.execute(
        """
        UPDATE entries e
        SET verification_state = 'verified',
            verification_reason = NULL,
            verified_at = v.created_at
        FROM verifications v
        WHERE v.entry_id = e.id;
        """
    )

    op.execute(
        """
        UPDATE entries e
        SET verification_state = 'legacy_gap',
            verification_reason = 'pushed_without_verification',
            verified_at = NULL
        WHERE e.verification_state IS NULL
          AND EXISTS (
              SELECT 1
              FROM push_events p
              WHERE p.entry_id = e.id
                AND p.status = 'sent'
          );
        """
    )

    op.execute(
        """
        UPDATE entries e
        SET verification_state = 'not_required',
            verification_reason = 'non_a',
            verified_at = NULL
        FROM scores s
        WHERE s.entry_id = e.id
          AND e.verification_state IS NULL
          AND s.grade <> 'A';
        """
    )

    op.execute(
        """
        UPDATE entries e
        SET verification_state = 'not_required',
            verification_reason = 'outside_push_window',
            verified_at = NULL
        FROM scores s
        WHERE s.entry_id = e.id
          AND e.verification_state IS NULL
          AND s.grade = 'A'
          AND COALESCE(e.published_at, e.created_at) < NOW() - INTERVAL '24 hours';
        """
    )

    op.execute(
        """
        UPDATE entries e
        SET verification_state = 'pending',
            verification_reason = 'eligible_for_verification',
            verified_at = NULL
        FROM scores s
        WHERE s.entry_id = e.id
          AND e.verification_state IS NULL
          AND s.grade = 'A';
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("entries")}

    op.drop_index("ix_entries_verification_state", table_name="entries", if_exists=True)

    if "verified_at" in existing_columns:
        op.drop_column("entries", "verified_at")
    if "verification_reason" in existing_columns:
        op.drop_column("entries", "verification_reason")
    if "verification_state" in existing_columns:
        op.drop_column("entries", "verification_state")
