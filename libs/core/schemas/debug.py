from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DebugCounts(BaseModel):
    entries: int
    quarantined_entries: int
    summaries: int
    scores: int
    verifications: int
    verification_pending: int
    verification_failed: int
    verification_not_required: int
    verification_legacy_gap: int
    push_events: int
    processed_telegram_updates: int
    daily_reports: int


class DebugEntryRow(BaseModel):
    id: int
    miniflux_entry_id: int
    title: str
    status: str
    quarantine_reason: str | None
    verification_state: str | None
    verification_reason: str | None
    verified_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    error: str | None


class DebugSummaryRow(BaseModel):
    entry_id: int
    summary_confidence: float
    model: str
    created_at: datetime


class DebugScoreRow(BaseModel):
    entry_id: int
    grade: str
    overall: float
    push_recommended: bool
    created_at: datetime


class DebugVerificationRow(BaseModel):
    entry_id: int
    verdict: str
    confidence: float
    created_at: datetime


class DebugVerificationCandidateRow(BaseModel):
    entry_id: int
    grade: str
    verification_state: str | None
    verification_reason: str | None
    published_at: datetime | None


class DebugPushEventRow(BaseModel):
    id: int
    entry_id: int | None
    type: str
    status: str
    telegram_chat_id: int
    telegram_message_id: int | None
    created_at: datetime
    error: str | None


class DebugProcessedUpdateRow(BaseModel):
    update_id: int
    created_at: datetime


class DebugOverviewResponse(BaseModel):
    generated_at: datetime
    counts: DebugCounts
    recent_entries: list[DebugEntryRow]
    recent_summaries: list[DebugSummaryRow]
    recent_scores: list[DebugScoreRow]
    recent_verifications: list[DebugVerificationRow]
    recent_verification_candidates: list[DebugVerificationCandidateRow]
    recent_push_events: list[DebugPushEventRow]
    recent_processed_updates: list[DebugProcessedUpdateRow]
