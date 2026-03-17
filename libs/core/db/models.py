from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from libs.core.db.base import Base
from libs.core.db.enums import (
    ContentFetchState,
    EntryStatus,
    FeedbackType,
    Grade,
    PushStatus,
    PushType,
    VerificationState,
    VerificationVerdict,
)


def _enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    miniflux_entry_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    miniflux_feed_id: Mapped[int | None] = mapped_column(BigInteger)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_html: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    lang: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[EntryStatus] = mapped_column(
        Enum(EntryStatus, name="entry_status", values_callable=_enum_values),
        default=EntryStatus.NEW,
        nullable=False,
    )
    quarantine_reason: Mapped[str | None] = mapped_column(Text)
    verification_state: Mapped[VerificationState | None] = mapped_column(
        Enum(VerificationState, name="verification_state", values_callable=_enum_values)
    )
    verification_reason: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_fetch_state: Mapped[ContentFetchState] = mapped_column(
        Enum(ContentFetchState, name="content_fetch_state", values_callable=_enum_values),
        default=ContentFetchState.READY,
        nullable=False,
    )
    content_fetch_fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_content_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_content_fetch_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_content_fetch_error: Mapped[str | None] = mapped_column(Text)
    last_process_outcome: Mapped[str | None] = mapped_column(Text)
    last_process_reason: Mapped[str | None] = mapped_column(Text)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


Index("ix_entries_published_at", Entry.published_at.desc())
Index("ix_entries_status", Entry.status)
Index("ix_entries_verification_state", Entry.verification_state)
Index("ix_entries_content_fetch_state", Entry.content_fetch_state)
Index("ix_entries_next_content_fetch_after", Entry.next_content_fetch_after)
Index("ix_entries_last_process_outcome", Entry.last_process_outcome)
Index("ix_entries_feed_published", Entry.miniflux_feed_id, Entry.published_at)


class EntryChunk(Base):
    __tablename__ = "entry_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


Index("ix_entry_chunks_entry_idx", EntryChunk.entry_id, EntryChunk.chunk_index)


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    tldr: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    ai_pm_takeaways: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    entities: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    risk_flags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    action_items: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    claims: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    summary_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    summary_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    relevance_agents: Mapped[float] = mapped_column(Float, nullable=False)
    relevance_eval: Mapped[float] = mapped_column(Float, nullable=False)
    relevance_product: Mapped[float] = mapped_column(Float, nullable=False)
    relevance_engineering: Mapped[float] = mapped_column(Float, nullable=False)
    relevance_biz: Mapped[float] = mapped_column(Float, nullable=False)
    novelty: Mapped[float] = mapped_column(Float, nullable=False)
    actionability: Mapped[float] = mapped_column(Float, nullable=False)
    credibility: Mapped[float] = mapped_column(Float, nullable=False)
    overall: Mapped[float] = mapped_column(Float, nullable=False)
    grade: Mapped[Grade] = mapped_column(
        Enum(Grade, name="grade", values_callable=_enum_values), nullable=False
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    push_recommended: Mapped[bool] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    verdict: Mapped[VerificationVerdict] = mapped_column(
        Enum(VerificationVerdict, name="verification_verdict", values_callable=_enum_values),
        nullable=False,
    )
    verified_claims: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    unverified_claims: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PushEvent(Base):
    __tablename__ = "push_events"
    __table_args__ = (
        UniqueConstraint("type", "entry_id", "telegram_chat_id", name="uq_push_alert_once"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[int | None] = mapped_column(ForeignKey("entries.id", ondelete="SET NULL"))
    type: Mapped[PushType] = mapped_column(
        Enum(PushType, name="push_type", values_callable=_enum_values), nullable=False
    )
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[PushStatus] = mapped_column(
        Enum(PushStatus, name="push_status", values_callable=_enum_values), nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IngestBatchRun(Base):
    __tablename__ = "ingest_batch_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scanned_count: Mapped[int] = mapped_column(Integer, nullable=False)
    actionable_count: Mapped[int] = mapped_column(Integer, nullable=False)
    marked_read_count: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_terminal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_cooldown_count: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_blocked_count: Mapped[int] = mapped_column(Integer, nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


Index("ix_ingest_batch_runs_finished_at", IngestBatchRun.finished_at.desc())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    context_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProcessedTelegramUpdate(Base):
    __tablename__ = "processed_telegram_updates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    update_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id", ondelete="CASCADE"), nullable=False)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    feedback: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType, name="feedback_type", values_callable=_enum_values), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
