from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DebugCounts(BaseModel):
    entries: int
    quarantined_entries: int
    fetch_cooldown_entries: int
    fetch_blocked_entries: int
    too_short_entries: int
    summaries: int
    scores: int
    verifications: int
    process_completed_entries: int
    process_quarantined_entries: int
    process_fetch_deferred_entries: int
    process_failed_entries: int
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
    content_fetch_state: str
    content_fetch_fail_count: int
    next_content_fetch_after: datetime | None
    last_content_fetch_error: str | None
    last_process_outcome: str | None
    last_process_reason: str | None
    last_processed_at: datetime | None
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
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    created_at: datetime


class DebugScoreRow(BaseModel):
    entry_id: int
    grade: str
    overall: float
    push_recommended: bool
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    created_at: datetime


class DebugVerificationRow(BaseModel):
    entry_id: int
    verdict: str
    confidence: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
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


class DebugTokenUsageRow(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class DebugLlmTokensLast24h(BaseModel):
    summary: DebugTokenUsageRow
    score: DebugTokenUsageRow
    verify: DebugTokenUsageRow


class DebugLatestIngestBatch(BaseModel):
    scanned_count: int
    actionable_count: int
    marked_read_count: int
    skipped_terminal_count: int
    skipped_cooldown_count: int
    skipped_blocked_count: int
    finished_at: datetime


class DebugOverviewResponse(BaseModel):
    generated_at: datetime
    counts: DebugCounts
    llm_tokens_last_24h: DebugLlmTokensLast24h
    latest_ingest_batch: DebugLatestIngestBatch | None
    recent_entries: list[DebugEntryRow]
    recent_summaries: list[DebugSummaryRow]
    recent_scores: list[DebugScoreRow]
    recent_verifications: list[DebugVerificationRow]
    recent_verification_candidates: list[DebugVerificationCandidateRow]
    recent_push_events: list[DebugPushEventRow]
    recent_processed_updates: list[DebugProcessedUpdateRow]
