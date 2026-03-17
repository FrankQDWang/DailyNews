"""add fetch state and llm usage telemetry

Revision ID: 0005_fetch_state_and_llm_usage
Revises: 0004_verification_state_audit
Create Date: 2026-03-17 19:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_fetch_state_and_llm_usage"
down_revision = "0004_verification_state_audit"
branch_labels = None
depends_on = None


TOKEN_TABLES = ("summaries", "scores", "verifications")
TOKEN_COLUMNS = ("prompt_tokens", "completion_tokens", "total_tokens")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE content_fetch_state AS ENUM (
                'ready',
                'cooldown',
                'blocked'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    existing_entry_columns = {column["name"] for column in inspector.get_columns("entries")}
    existing_entry_indexes = {index["name"] for index in inspector.get_indexes("entries")}
    content_fetch_state_enum = sa.Enum(
        "ready",
        "cooldown",
        "blocked",
        name="content_fetch_state",
        create_type=False,
    )

    if "content_fetch_state" not in existing_entry_columns:
        op.add_column(
            "entries",
            sa.Column(
                "content_fetch_state",
                content_fetch_state_enum,
                nullable=False,
                server_default="ready",
            ),
        )
    if "content_fetch_fail_count" not in existing_entry_columns:
        op.add_column(
            "entries",
            sa.Column("content_fetch_fail_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "last_content_fetch_at" not in existing_entry_columns:
        op.add_column(
            "entries",
            sa.Column("last_content_fetch_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "next_content_fetch_after" not in existing_entry_columns:
        op.add_column(
            "entries",
            sa.Column("next_content_fetch_after", sa.DateTime(timezone=True), nullable=True),
        )
    if "last_content_fetch_error" not in existing_entry_columns:
        op.add_column("entries", sa.Column("last_content_fetch_error", sa.Text(), nullable=True))

    if "ix_entries_content_fetch_state" not in existing_entry_indexes:
        op.create_index(
            "ix_entries_content_fetch_state",
            "entries",
            ["content_fetch_state"],
            unique=False,
        )
    if "ix_entries_next_content_fetch_after" not in existing_entry_indexes:
        op.create_index(
            "ix_entries_next_content_fetch_after",
            "entries",
            ["next_content_fetch_after"],
            unique=False,
        )

    for table_name in TOKEN_TABLES:
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "prompt_tokens" not in existing_columns:
            op.add_column(table_name, sa.Column("prompt_tokens", sa.Integer(), nullable=True))
        if "completion_tokens" not in existing_columns:
            op.add_column(table_name, sa.Column("completion_tokens", sa.Integer(), nullable=True))
        if "total_tokens" not in existing_columns:
            op.add_column(table_name, sa.Column("total_tokens", sa.Integer(), nullable=True))

    op.execute("UPDATE entries SET content_fetch_state = 'ready' WHERE content_fetch_state IS NULL")
    op.execute("UPDATE entries SET content_fetch_fail_count = 0 WHERE content_fetch_fail_count IS NULL")

    op.alter_column("entries", "content_fetch_state", server_default=None)
    op.alter_column("entries", "content_fetch_fail_count", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name in TOKEN_TABLES:
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name in TOKEN_COLUMNS:
            if column_name in existing_columns:
                op.drop_column(table_name, column_name)

    existing_entry_columns = {column["name"] for column in inspector.get_columns("entries")}
    op.drop_index("ix_entries_next_content_fetch_after", table_name="entries", if_exists=True)
    op.drop_index("ix_entries_content_fetch_state", table_name="entries", if_exists=True)

    for column_name in (
        "last_content_fetch_error",
        "next_content_fetch_after",
        "last_content_fetch_at",
        "content_fetch_fail_count",
        "content_fetch_state",
    ):
        if column_name in existing_entry_columns:
            op.drop_column("entries", column_name)
