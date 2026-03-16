"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-03-05 22:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Pre-create named enums and stop SQLAlchemy from trying to re-create them
    # during table DDL. This keeps the initial migration rerunnable on a partially
    # initialized database.
    entry_status = postgresql.ENUM(
        "new",
        "summarized",
        "scored",
        "verified",
        "pushed",
        "failed",
        name="entry_status",
        create_type=False,
    )
    grade = postgresql.ENUM("A", "B", "C", name="grade", create_type=False)
    verification_verdict = postgresql.ENUM(
        "verified",
        "partially_verified",
        "uncertain",
        name="verification_verdict",
        create_type=False,
    )
    push_type = postgresql.ENUM("alert", "digest", "reply", name="push_type", create_type=False)
    push_status = postgresql.ENUM("sent", "failed", name="push_status", create_type=False)
    feedback_type = postgresql.ENUM(
        "up",
        "down",
        "save",
        "mute_source",
        name="feedback_type",
        create_type=False,
    )

    entry_status.create(op.get_bind(), checkfirst=True)
    grade.create(op.get_bind(), checkfirst=True)
    verification_verdict.create(op.get_bind(), checkfirst=True)
    push_type.create(op.get_bind(), checkfirst=True)
    push_status.create(op.get_bind(), checkfirst=True)
    feedback_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("miniflux_entry_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("miniflux_feed_id", sa.BigInteger(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_html", sa.Text(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("lang", sa.String(length=32), nullable=True),
        sa.Column("status", entry_status, nullable=False, server_default="new"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_entries_published_at", "entries", [sa.text("published_at DESC")])
    op.create_index("ix_entries_status", "entries", ["status"])
    op.create_index("ix_entries_feed_published", "entries", ["miniflux_feed_id", "published_at"])

    op.create_table(
        "entry_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.BigInteger(), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_entry_chunks_entry_idx", "entry_chunks", ["entry_id", "chunk_index"])

    op.create_table(
        "summaries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.BigInteger(), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("tldr", sa.Text(), nullable=False),
        sa.Column("key_points", sa.JSON(), nullable=False),
        sa.Column("ai_pm_takeaways", sa.JSON(), nullable=False),
        sa.Column("tags", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("entities", sa.JSON(), nullable=False),
        sa.Column("risk_flags", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("action_items", sa.JSON(), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("summary_confidence", sa.Float(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "scores",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.BigInteger(), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("relevance_agents", sa.Float(), nullable=False),
        sa.Column("relevance_eval", sa.Float(), nullable=False),
        sa.Column("relevance_product", sa.Float(), nullable=False),
        sa.Column("relevance_engineering", sa.Float(), nullable=False),
        sa.Column("relevance_biz", sa.Float(), nullable=False),
        sa.Column("novelty", sa.Float(), nullable=False),
        sa.Column("actionability", sa.Float(), nullable=False),
        sa.Column("credibility", sa.Float(), nullable=False),
        sa.Column("overall", sa.Float(), nullable=False),
        sa.Column("grade", grade, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("push_recommended", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "verifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.BigInteger(), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("verdict", verification_verdict, nullable=False),
        sa.Column("verified_claims", sa.JSON(), nullable=False),
        sa.Column("unverified_claims", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "push_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.BigInteger(), sa.ForeignKey("entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", push_type, nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", push_status, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("type", "entry_id", "telegram_chat_id", name="uq_push_alert_once"),
    )

    op.create_table(
        "daily_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_markdown", sa.Text(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "user_feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.BigInteger(), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("feedback", feedback_type, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_feedback")
    op.drop_table("chat_sessions")
    op.drop_table("daily_reports")
    op.drop_table("push_events")
    op.drop_table("verifications")
    op.drop_table("scores")
    op.drop_table("summaries")
    op.drop_index("ix_entry_chunks_entry_idx", table_name="entry_chunks")
    op.drop_table("entry_chunks")
    op.drop_index("ix_entries_feed_published", table_name="entries")
    op.drop_index("ix_entries_status", table_name="entries")
    op.drop_index("ix_entries_published_at", table_name="entries")
    op.drop_table("entries")

    sa.Enum(name="feedback_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="push_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="push_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="verification_verdict").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="grade").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="entry_status").drop(op.get_bind(), checkfirst=True)
