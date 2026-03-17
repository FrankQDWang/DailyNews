from __future__ import annotations

import html
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from libs.core.db.enums import (
    ContentFetchState,
    EntryStatus,
    Grade,
    PushStatus,
    PushType,
    VerificationState,
    VerificationVerdict,
)
from libs.core.db.models import Entry, Score, Summary, Verification
from libs.core.db.repositories import (
    PROCESS_REASON_SCORED_NO_PUSH,
    create_push_event,
    get_entry_for_processing,
    get_latest_report,
    get_score,
    get_summary,
    mark_entry_completed,
    mark_entry_failed,
    mark_entry_pushed,
    quarantine_entry,
    query_for_rag,
    record_content_fetch_failure,
    save_daily_report,
    save_entry_content,
    save_ingest_batch_run,
    save_score,
    save_summary,
    save_verification,
    set_process_outcome,
    set_verification_state,
    upsert_entry,
)
from libs.core.db.session import SessionFactory
from libs.core.metrics import (
    MINIFLUX_FETCH_CONTENT_ATTEMPT_TOTAL,
    MINIFLUX_FETCH_CONTENT_BLOCKED_TOTAL,
    MINIFLUX_FETCH_CONTENT_FAILURES,
    MINIFLUX_FETCH_CONTENT_SKIPPED_TOTAL,
    NEW_ENTRIES_FOUND,
    TASKS_TOTAL,
)
from libs.core.settings import get_settings
from libs.integrations.deepseek_client import DeepSeekClient
from libs.integrations.miniflux_client import (
    MinifluxClient,
    MinifluxEntry,
    MinifluxEntryPayload,
    serialize_entries,
)
from libs.integrations.tavily_client import TavilyClient
from libs.integrations.telegram_client import TelegramClient
from libs.workflows.contracts import (
    IngestEntryResult,
    PreparedIngestBatchResult,
    PrepareEntryContentResult,
)

logger = logging.getLogger(__name__)
settings = get_settings()
PROCESSABLE_ENTRY_STATUSES = frozenset(
    {EntryStatus.NEW, EntryStatus.SUMMARIZED, EntryStatus.FAILED}
)
EMPTY_CONTENT_REASON = "empty_content"
TOO_SHORT_CONTENT_REASON = "too_short_content"
ZERO_WIDTH_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff")
MIN_CONTENT_LENGTH = 280
FETCH_SKIP_REASON_TERMINAL = "terminal_status"
FETCH_SKIP_REASON_COOLDOWN = "cooldown"
FETCH_SKIP_REASON_BLOCKED = "blocked"
PUSH_DECISION_REASON_NON_A = "non_a"
PUSH_DECISION_REASON_OUTSIDE_WINDOW = "outside_push_window"
PUSH_DECISION_REASON_DAILY_CAP = "daily_cap_reached"
PUSH_DECISION_REASON_ELIGIBLE = "eligible_for_verification"
PREPARE_ENTRY_STATUS_READY = "ready"
PREPARE_ENTRY_STATUS_QUARANTINED = "quarantined"
PREPARE_ENTRY_STATUS_FETCH_DEFERRED = "fetch_deferred"


def _grade_is_a(score: str) -> bool:
    return score.upper() == Grade.A.value


@activity.defn
async def refresh_miniflux_activity() -> None:
    TASKS_TOTAL.labels(type="refresh_miniflux").inc()
    client = MinifluxClient(settings)
    try:
        await client.refresh_feeds()
        logger.info("Miniflux refresh completed")
    finally:
        await client.close()


@activity.defn
async def list_unread_miniflux_activity(limit: int = 100) -> list[MinifluxEntryPayload]:
    TASKS_TOTAL.labels(type="list_unread_miniflux").inc()
    client = MinifluxClient(settings)
    try:
        entries = await client.list_unread_entries(limit=limit)
    finally:
        await client.close()

    NEW_ENTRIES_FOUND.inc(len(entries))
    logger.info("Fetched %d unread Miniflux entries", len(entries))
    return serialize_entries(entries)


@activity.defn
async def prepare_ingest_batch_activity(
    scan_limit: int,
    actionable_limit: int,
) -> PreparedIngestBatchResult:
    TASKS_TOTAL.labels(type="prepare_ingest_batch").inc()
    client = MinifluxClient(settings)
    try:
        unread_entries = await client.list_unread_entries(limit=scan_limit)
    finally:
        await client.close()

    NEW_ENTRIES_FOUND.inc(len(unread_entries))
    scanned_count = len(unread_entries)
    actionable_entry_ids: list[int] = []
    mark_read_miniflux_entry_ids: list[int] = []
    skipped_terminal_count = 0
    skipped_cooldown_count = 0
    skipped_blocked_count = 0

    async with SessionFactory() as session:
        for unread_entry in unread_entries:
            db_entry_id = await upsert_entry(
                session,
                miniflux_entry_id=int(unread_entry.id),
                miniflux_feed_id=int(unread_entry.feed_id) if unread_entry.feed_id is not None else None,
                url=str(unread_entry.url),
                title=str(unread_entry.title),
                author=str(unread_entry.author) if unread_entry.author is not None else None,
                published_at=unread_entry.published_at,
                fetched_at=None,
                content_html=None,
                content_text=None,
            )
            db_entry = await get_entry_for_processing(session, db_entry_id)
            if db_entry is None:
                raise RuntimeError(f"Entry not found after metadata upsert: {db_entry_id}")
            ingest_result = _build_ingest_entry_result(db_entry)
            if ingest_result["needs_processing"]:
                if len(actionable_entry_ids) < actionable_limit:
                    actionable_entry_ids.append(int(db_entry.id))
                continue
            if db_entry.content_fetch_state == ContentFetchState.BLOCKED:
                skipped_blocked_count += 1
            elif (
                db_entry.content_fetch_state == ContentFetchState.COOLDOWN
                and db_entry.next_content_fetch_after is not None
                and db_entry.next_content_fetch_after > datetime.now(UTC)
            ):
                skipped_cooldown_count += 1
            else:
                skipped_terminal_count += 1
            if ingest_result["should_mark_read"]:
                mark_read_miniflux_entry_ids.append(int(db_entry.miniflux_entry_id))

    marked_read_count = await _mark_entries_read_in_batches(mark_read_miniflux_entry_ids)
    async with SessionFactory() as session:
        await save_ingest_batch_run(
            session,
            scanned_count=scanned_count,
            actionable_count=len(actionable_entry_ids),
            marked_read_count=marked_read_count,
            skipped_terminal_count=skipped_terminal_count,
            skipped_cooldown_count=skipped_cooldown_count,
            skipped_blocked_count=skipped_blocked_count,
            finished_at=datetime.now(UTC),
        )

    logger.info(
        "Prepared ingest batch scanned=%s actionable=%s marked_read=%s skipped_terminal=%s skipped_cooldown=%s skipped_blocked=%s",
        scanned_count,
        len(actionable_entry_ids),
        marked_read_count,
        skipped_terminal_count,
        skipped_cooldown_count,
        skipped_blocked_count,
    )
    return {
        "actionable_entry_ids": actionable_entry_ids,
        "marked_read_count": marked_read_count,
        "scanned_count": scanned_count,
        "actionable_count": len(actionable_entry_ids),
        "skipped_terminal_count": skipped_terminal_count,
        "skipped_cooldown_count": skipped_cooldown_count,
        "skipped_blocked_count": skipped_blocked_count,
    }


@activity.defn
async def fetch_and_upsert_entry_activity(
    entry_payload: MinifluxEntryPayload,
) -> dict[str, str | int | bool | None] | int:
    TASKS_TOTAL.labels(type="fetch_and_upsert_entry").inc()
    src = _payload_to_entry(entry_payload)

    async with SessionFactory() as session:
        db_entry_id = await upsert_entry(
            session,
            miniflux_entry_id=src["id"],
            miniflux_feed_id=src["feed_id"],
            url=src["url"],
            title=src["title"],
            author=src["author"],
            published_at=src["published_at"],
            fetched_at=None,
            content_html=src["content"],
            content_text=src["content"],
        )
        db_entry = await get_entry_for_processing(session, db_entry_id)
        if db_entry is None:
            raise RuntimeError(f"Entry not found after upsert: {db_entry_id}")
        ingest_result = _build_ingest_entry_result(db_entry)
        if not ingest_result["needs_processing"]:
            if db_entry.content_fetch_state == ContentFetchState.BLOCKED:
                MINIFLUX_FETCH_CONTENT_SKIPPED_TOTAL.labels(reason=FETCH_SKIP_REASON_BLOCKED).inc()
            elif (
                db_entry.content_fetch_state == ContentFetchState.COOLDOWN
                and db_entry.next_content_fetch_after is not None
                and db_entry.next_content_fetch_after > datetime.now(UTC)
            ):
                MINIFLUX_FETCH_CONTENT_SKIPPED_TOTAL.labels(reason=FETCH_SKIP_REASON_COOLDOWN).inc()
            else:
                MINIFLUX_FETCH_CONTENT_SKIPPED_TOTAL.labels(reason=FETCH_SKIP_REASON_TERMINAL).inc()
            logger.info(
                "Skipped fetch-content for database entry %s status=%s fetch_state=%s",
                db_entry_id,
                db_entry.status.value,
                db_entry.content_fetch_state.value,
            )
            return ingest_result

        fetched = await _fetch_content_from_miniflux(src["id"])
        if isinstance(fetched, Exception):
            if _is_retryable_fetch_failure(fetched):
                MINIFLUX_FETCH_CONTENT_FAILURES.inc()
                next_state = await record_content_fetch_failure(
                    session,
                    db_entry_id,
                    error=_format_fetch_error(fetched),
                    at=datetime.now(UTC),
                )
                if next_state == ContentFetchState.BLOCKED:
                    MINIFLUX_FETCH_CONTENT_BLOCKED_TOTAL.inc()
                db_entry = await get_entry_for_processing(session, db_entry_id)
                if db_entry is None:
                    raise RuntimeError(f"Entry not found after fetch failure: {db_entry_id}")
                logger.warning(
                    "Fetch-content failed for entry %s; state=%s error=%s",
                    db_entry_id,
                    next_state.value,
                    fetched,
                )
                return _build_ingest_entry_result(db_entry)
            raise fetched

        fetched_record = _miniflux_entry_to_record(fetched)
        await save_entry_content(
            session,
            db_entry_id,
            content_html=fetched_record["content"],
            content_text=fetched_record["content"],
            fetched_at=datetime.now(UTC),
        )
        db_entry = await get_entry_for_processing(session, db_entry_id)
        if db_entry is None:
            raise RuntimeError(f"Entry not found after saving fetched content: {db_entry_id}")
        if _is_empty_content(fetched_record["content"]):
            await quarantine_entry(session, db_entry_id, EMPTY_CONTENT_REASON)
            db_entry = await get_entry_for_processing(session, db_entry_id)
            if db_entry is None:
                raise RuntimeError(f"Entry not found after quarantine: {db_entry_id}")
            logger.info("Quarantined entry %s due to %s", db_entry_id, EMPTY_CONTENT_REASON)
            return _build_ingest_entry_result(db_entry)
        if _is_too_short_content(fetched_record["content"]):
            await quarantine_entry(session, db_entry_id, TOO_SHORT_CONTENT_REASON)
            db_entry = await get_entry_for_processing(session, db_entry_id)
            if db_entry is None:
                raise RuntimeError(f"Entry not found after quarantine: {db_entry_id}")
            logger.info("Quarantined entry %s due to %s", db_entry_id, TOO_SHORT_CONTENT_REASON)
            return _build_ingest_entry_result(db_entry)
        logger.info("Fetched and upserted Miniflux entry %s as database entry %s", src["id"], db_entry_id)
        return _build_ingest_entry_result(db_entry)


def _payload_to_entry(payload: MinifluxEntryPayload) -> dict[str, Any]:
    published = payload.get("published_at")
    published_at = None
    if isinstance(published, str):
        published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
    return {
        "id": int(payload["id"]),
        "feed_id": int(payload["feed_id"]) if payload.get("feed_id") else None,
        "url": str(payload.get("url", "")),
        "title": str(payload.get("title", "")),
        "author": str(payload["author"]) if payload.get("author") else None,
        "published_at": published_at,
        "content": str(payload["content"]) if payload.get("content") else "",
    }


def _miniflux_entry_to_record(entry: MinifluxEntry) -> dict[str, Any]:
    return {
        "id": int(entry.id),
        "feed_id": int(entry.feed_id) if entry.feed_id is not None else None,
        "url": str(entry.url),
        "title": str(entry.title),
        "author": str(entry.author) if entry.author is not None else None,
        "published_at": entry.published_at,
        "content": str(entry.content) if entry.content else "",
    }


def _build_ingest_entry_result(entry: Entry) -> IngestEntryResult:
    return {
        "entry_id": int(entry.id),
        "miniflux_entry_id": int(entry.miniflux_entry_id),
        "published_at": entry.published_at.isoformat() if entry.published_at is not None else None,
        "current_status": entry.status.value,
        "needs_processing": _needs_processing(entry.status) and _fetch_content_is_actionable(entry),
        "should_mark_read": _should_mark_read_without_processing(entry),
    }


def _build_prepare_entry_content_result(
    *,
    status: str,
    reason: str,
    marked_read: bool,
    content_fetch_state: ContentFetchState,
) -> PrepareEntryContentResult:
    return {
        "status": status,
        "reason": reason,
        "marked_read": marked_read,
        "content_fetch_state": content_fetch_state.value,
    }


def _has_usable_entry_content(entry: Entry) -> bool:
    return not _is_empty_content(entry.content_text) and not _is_too_short_content(entry.content_text)


def _deferred_process_reason(fetch_state: ContentFetchState, error: str | None = None) -> str:
    if error is None:
        return fetch_state.value
    return f"{fetch_state.value}:{error}"


async def _mark_entries_read_in_batches(entry_ids: list[int], batch_size: int = 100) -> int:
    unique_entry_ids = list(dict.fromkeys(entry_ids))
    if not unique_entry_ids:
        return 0
    client = MinifluxClient(settings)
    marked_read_count = 0
    try:
        for start in range(0, len(unique_entry_ids), batch_size):
            batch = unique_entry_ids[start : start + batch_size]
            try:
                await client.mark_entries_read(batch)
                marked_read_count += len(batch)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to mark Miniflux entries as read in batch: %s", exc)
    finally:
        await client.close()
    return marked_read_count


async def _fetch_content_from_miniflux(entry_id: int) -> MinifluxEntry | Exception:
    MINIFLUX_FETCH_CONTENT_ATTEMPT_TOTAL.inc()
    client = MinifluxClient(settings)
    try:
        return await client.fetch_content(entry_id)
    except Exception as exc:  # noqa: BLE001
        return exc
    finally:
        await client.close()


def _needs_processing(status: EntryStatus) -> bool:
    return status in PROCESSABLE_ENTRY_STATUSES


def _should_mark_read_without_processing(entry: Entry) -> bool:
    if entry.status in {
        EntryStatus.SCORED,
        EntryStatus.VERIFIED,
        EntryStatus.PUSHED,
        EntryStatus.QUARANTINED,
    }:
        return True
    if entry.content_fetch_state == ContentFetchState.BLOCKED:
        return True
    return False


def _fetch_content_is_actionable(entry: Entry) -> bool:
    if entry.content_fetch_state == ContentFetchState.READY:
        return True
    if entry.content_fetch_state != ContentFetchState.COOLDOWN:
        return False
    if entry.next_content_fetch_after is None:
        return True
    return entry.next_content_fetch_after <= datetime.now(UTC)


def _entry_reference_time(entry: Entry) -> datetime:
    return entry.published_at or entry.created_at


def _is_within_push_window(entry: Entry, *, now: datetime, window_hours: int) -> bool:
    reference_time = _entry_reference_time(entry)
    threshold = now - timedelta(hours=window_hours)
    return reference_time >= threshold


def _normalize_content(raw: str | None) -> str:
    if raw is None:
        return ""
    normalized = html.unescape(str(raw)).replace("\u00a0", " ")
    for char in ZERO_WIDTH_CHARS:
        normalized = normalized.replace(char, "")
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.strip()


def _is_empty_content(raw: str | None) -> bool:
    return _normalize_content(raw) == ""


def _normalized_content_length(raw: str | None) -> int:
    return len(_normalize_content(raw))


def _is_too_short_content(raw: str | None) -> bool:
    normalized = _normalize_content(raw)
    return normalized != "" and len(normalized) < MIN_CONTENT_LENGTH


def _is_retryable_fetch_failure(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or 500 <= status_code < 600
    return False


def _format_fetch_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_status:{exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError):
        return f"transport:{exc.__class__.__name__}"
    return str(exc)


async def _sync_miniflux_read_for_entry(
    entry: Entry, *, after_quarantine: bool = False
) -> bool:
    miniflux_entry_id = int(entry.miniflux_entry_id)
    client = MinifluxClient(settings)
    try:
        await client.mark_entries_read([miniflux_entry_id])
        if after_quarantine:
            logger.info(
                "Marked Miniflux entry %s as read after quarantine for database entry %s",
                miniflux_entry_id,
                entry.id,
            )
        else:
            logger.info(
                "Marked Miniflux entry %s as read for database entry %s",
                miniflux_entry_id,
                entry.id,
            )
        return True
    except Exception as exc:  # noqa: BLE001
        if after_quarantine:
            logger.warning(
                "Failed to mark Miniflux entry %s as read after quarantine for database entry %s: %s",
                miniflux_entry_id,
                entry.id,
                exc,
            )
        else:
            logger.warning(
                "Failed to mark Miniflux entry %s as read for database entry %s: %s",
                miniflux_entry_id,
                entry.id,
                exc,
            )
        return False
    finally:
        await client.close()


@activity.defn
async def prepare_entry_content_activity(entry_id: int) -> PrepareEntryContentResult:
    TASKS_TOTAL.labels(type="prepare_entry_content").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        if entry is None:
            raise RuntimeError(f"Entry not found: {entry_id}")

        if entry.content_fetch_state == ContentFetchState.BLOCKED:
            marked_read = await _sync_miniflux_read_for_entry(entry, after_quarantine=False)
            reason = _deferred_process_reason(ContentFetchState.BLOCKED)
            await set_process_outcome(session, entry_id, PREPARE_ENTRY_STATUS_FETCH_DEFERRED, reason)
            logger.info("Process entry %s deferred: %s", entry_id, reason)
            return _build_prepare_entry_content_result(
                status=PREPARE_ENTRY_STATUS_FETCH_DEFERRED,
                reason=reason,
                marked_read=marked_read,
                content_fetch_state=ContentFetchState.BLOCKED,
            )

        if (
            entry.content_fetch_state == ContentFetchState.COOLDOWN
            and entry.next_content_fetch_after is not None
            and entry.next_content_fetch_after > datetime.now(UTC)
        ):
            reason = _deferred_process_reason(ContentFetchState.COOLDOWN)
            await set_process_outcome(session, entry_id, PREPARE_ENTRY_STATUS_FETCH_DEFERRED, reason)
            logger.info("Process entry %s deferred: %s", entry_id, reason)
            return _build_prepare_entry_content_result(
                status=PREPARE_ENTRY_STATUS_FETCH_DEFERRED,
                reason=reason,
                marked_read=False,
                content_fetch_state=ContentFetchState.COOLDOWN,
            )

        if entry.content_text is not None and _is_empty_content(entry.content_text):
            await quarantine_entry(session, entry_id, EMPTY_CONTENT_REASON)
            entry = await get_entry_for_processing(session, entry_id)
            if entry is None:
                raise RuntimeError(f"Entry not found after empty-content quarantine: {entry_id}")
            marked_read = await _sync_miniflux_read_for_entry(entry, after_quarantine=True)
            logger.info("Process entry %s quarantined: %s", entry_id, EMPTY_CONTENT_REASON)
            return _build_prepare_entry_content_result(
                status=PREPARE_ENTRY_STATUS_QUARANTINED,
                reason=EMPTY_CONTENT_REASON,
                marked_read=marked_read,
                content_fetch_state=entry.content_fetch_state,
            )

        if entry.content_text is not None and _is_too_short_content(entry.content_text):
            await quarantine_entry(session, entry_id, TOO_SHORT_CONTENT_REASON)
            entry = await get_entry_for_processing(session, entry_id)
            if entry is None:
                raise RuntimeError(f"Entry not found after too-short quarantine: {entry_id}")
            marked_read = await _sync_miniflux_read_for_entry(entry, after_quarantine=True)
            logger.info("Process entry %s quarantined: %s", entry_id, TOO_SHORT_CONTENT_REASON)
            return _build_prepare_entry_content_result(
                status=PREPARE_ENTRY_STATUS_QUARANTINED,
                reason=TOO_SHORT_CONTENT_REASON,
                marked_read=marked_read,
                content_fetch_state=entry.content_fetch_state,
            )

        if _has_usable_entry_content(entry):
            return _build_prepare_entry_content_result(
                status=PREPARE_ENTRY_STATUS_READY,
                reason="content_ready",
                marked_read=False,
                content_fetch_state=entry.content_fetch_state,
            )

        fetched = await _fetch_content_from_miniflux(int(entry.miniflux_entry_id))
        if isinstance(fetched, Exception):
            if _is_retryable_fetch_failure(fetched):
                MINIFLUX_FETCH_CONTENT_FAILURES.inc()
                fetch_error = _format_fetch_error(fetched)
                next_state = await record_content_fetch_failure(
                    session,
                    entry_id,
                    error=fetch_error,
                    at=datetime.now(UTC),
                )
                entry = await get_entry_for_processing(session, entry_id)
                if entry is None:
                    raise RuntimeError(f"Entry not found after prepare fetch failure: {entry_id}")
                marked_read = False
                if next_state == ContentFetchState.BLOCKED:
                    MINIFLUX_FETCH_CONTENT_BLOCKED_TOTAL.inc()
                    marked_read = await _sync_miniflux_read_for_entry(entry, after_quarantine=False)
                reason = _deferred_process_reason(next_state, fetch_error)
                await set_process_outcome(
                    session,
                    entry_id,
                    PREPARE_ENTRY_STATUS_FETCH_DEFERRED,
                    reason,
                )
                logger.info("Process entry %s deferred: %s", entry_id, reason)
                return _build_prepare_entry_content_result(
                    status=PREPARE_ENTRY_STATUS_FETCH_DEFERRED,
                    reason=reason,
                    marked_read=marked_read,
                    content_fetch_state=next_state,
                )
            raise fetched

        fetched_record = _miniflux_entry_to_record(fetched)
        await save_entry_content(
            session,
            entry_id,
            content_html=fetched_record["content"],
            content_text=fetched_record["content"],
            fetched_at=datetime.now(UTC),
        )
        entry = await get_entry_for_processing(session, entry_id)
        if entry is None:
            raise RuntimeError(f"Entry not found after prepare fetch save: {entry_id}")
        if _is_empty_content(entry.content_text):
            await quarantine_entry(session, entry_id, EMPTY_CONTENT_REASON)
            entry = await get_entry_for_processing(session, entry_id)
            if entry is None:
                raise RuntimeError(f"Entry not found after empty-content quarantine: {entry_id}")
            marked_read = await _sync_miniflux_read_for_entry(entry, after_quarantine=True)
            logger.info("Process entry %s quarantined: %s", entry_id, EMPTY_CONTENT_REASON)
            return _build_prepare_entry_content_result(
                status=PREPARE_ENTRY_STATUS_QUARANTINED,
                reason=EMPTY_CONTENT_REASON,
                marked_read=marked_read,
                content_fetch_state=entry.content_fetch_state,
            )
        if _is_too_short_content(entry.content_text):
            await quarantine_entry(session, entry_id, TOO_SHORT_CONTENT_REASON)
            entry = await get_entry_for_processing(session, entry_id)
            if entry is None:
                raise RuntimeError(f"Entry not found after too-short quarantine: {entry_id}")
            marked_read = await _sync_miniflux_read_for_entry(entry, after_quarantine=True)
            logger.info("Process entry %s quarantined: %s", entry_id, TOO_SHORT_CONTENT_REASON)
            return _build_prepare_entry_content_result(
                status=PREPARE_ENTRY_STATUS_QUARANTINED,
                reason=TOO_SHORT_CONTENT_REASON,
                marked_read=marked_read,
                content_fetch_state=entry.content_fetch_state,
            )
        return _build_prepare_entry_content_result(
            status=PREPARE_ENTRY_STATUS_READY,
            reason="content_fetched",
            marked_read=False,
            content_fetch_state=entry.content_fetch_state,
        )


@activity.defn
async def summarize_entry_activity(entry_id: int) -> dict[str, Any]:
    TASKS_TOTAL.labels(type="summarize_entry").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        if not entry:
            raise RuntimeError(f"Entry not found: {entry_id}")
        existing_summary = await get_summary(session, entry_id)
        if existing_summary is not None:
            return existing_summary.summary_json

        if entry.content_fetch_state == ContentFetchState.BLOCKED:
            raise ApplicationError(
                f"Entry {entry_id} fetch-content is blocked",
                non_retryable=True,
            )
        if (
            entry.content_fetch_state == ContentFetchState.COOLDOWN
            and entry.next_content_fetch_after is not None
            and entry.next_content_fetch_after > datetime.now(UTC)
        ):
            raise ApplicationError(
                f"Entry {entry_id} fetch-content is cooling down until {entry.next_content_fetch_after.isoformat()}",
                non_retryable=True,
            )
        if _is_empty_content(entry.content_text) or entry.content_text is None:
            fetched = await _fetch_content_from_miniflux(int(entry.miniflux_entry_id))
            if isinstance(fetched, Exception):
                if _is_retryable_fetch_failure(fetched):
                    MINIFLUX_FETCH_CONTENT_FAILURES.inc()
                    next_state = await record_content_fetch_failure(
                        session,
                        entry_id,
                        error=_format_fetch_error(fetched),
                        at=datetime.now(UTC),
                    )
                    entry = await get_entry_for_processing(session, entry_id)
                    if entry is None:
                        raise RuntimeError(f"Entry not found after summarize fetch failure: {entry_id}")
                    if next_state == ContentFetchState.BLOCKED:
                        MINIFLUX_FETCH_CONTENT_BLOCKED_TOTAL.inc()
                        await _sync_miniflux_read_for_entry(entry, after_quarantine=False)
                    raise ApplicationError(
                        f"Entry {entry_id} fetch-content failed: {_format_fetch_error(fetched)}",
                        non_retryable=True,
                    )
                raise fetched
            fetched_record = _miniflux_entry_to_record(fetched)
            await save_entry_content(
                session,
                entry_id,
                content_html=fetched_record["content"],
                content_text=fetched_record["content"],
                fetched_at=datetime.now(UTC),
            )
            entry = await get_entry_for_processing(session, entry_id)
            if entry is None:
                raise RuntimeError(f"Entry not found after summarize fetch save: {entry_id}")

        if _is_empty_content(entry.content_text):
            await quarantine_entry(session, entry_id, EMPTY_CONTENT_REASON)
            entry = await get_entry_for_processing(session, entry_id)
            if entry is None:
                raise RuntimeError(f"Entry not found after empty-content quarantine: {entry_id}")
            logger.info("Quarantined entry %s due to %s", entry_id, EMPTY_CONTENT_REASON)
            await _sync_miniflux_read_for_entry(entry, after_quarantine=True)
            raise ApplicationError(
                f"Entry {entry_id} quarantined due to empty content",
                non_retryable=True,
            )
        if _is_too_short_content(entry.content_text):
            await quarantine_entry(session, entry_id, TOO_SHORT_CONTENT_REASON)
            entry = await get_entry_for_processing(session, entry_id)
            if entry is None:
                raise RuntimeError(f"Entry not found after too-short quarantine: {entry_id}")
            logger.info("Quarantined entry %s due to %s", entry_id, TOO_SHORT_CONTENT_REASON)
            await _sync_miniflux_read_for_entry(entry, after_quarantine=True)
            raise ApplicationError(
                f"Entry {entry_id} quarantined due to too-short content",
                non_retryable=True,
            )

        client = DeepSeekClient(settings)
        try:
            output, usage = await client.summarize(entry.title, entry.url, entry.content_text or "")
            await save_summary(session, entry_id, output, settings.llm_model_summary, usage)
            return output.model_dump()
        except ApplicationError:
            raise
        except Exception as exc:  # noqa: BLE001
            await mark_entry_failed(session, entry_id, f"summarize failed: {exc}")
            raise
        finally:
            await client.close()


@activity.defn
async def score_entry_activity(entry_id: int) -> dict[str, Any]:
    TASKS_TOTAL.labels(type="score_entry").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        summary = await get_summary(session, entry_id)
        existing_score = await get_score(session, entry_id)
        if not entry or not summary:
            raise RuntimeError(f"Missing entry/summary for {entry_id}")
        if existing_score is not None:
            return {
                "relevance": {
                    "agents": existing_score.relevance_agents,
                    "eval": existing_score.relevance_eval,
                    "product": existing_score.relevance_product,
                    "engineering": existing_score.relevance_engineering,
                    "biz": existing_score.relevance_biz,
                },
                "novelty": existing_score.novelty,
                "actionability": existing_score.actionability,
                "credibility": existing_score.credibility,
                "overall": existing_score.overall,
                "grade": existing_score.grade.value,
                "rationale": existing_score.rationale,
                "push_recommended": existing_score.push_recommended,
            }

        client = DeepSeekClient(settings)
        try:
            output, usage = await client.score(entry.title, entry.url, summary.summary_json)
            await save_score(session, entry_id, output, settings.llm_model_score, usage)
            return output.model_dump()
        except Exception as exc:  # noqa: BLE001
            await mark_entry_failed(session, entry_id, f"score failed: {exc}")
            raise
        finally:
            await client.close()


@activity.defn
async def mark_entry_read_activity(entry_id: int) -> bool:
    TASKS_TOTAL.labels(type="mark_entry_read").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        if entry is None:
            logger.warning("Skipping Miniflux read sync because entry %s does not exist", entry_id)
            return False
    return await _sync_miniflux_read_for_entry(
        entry,
        after_quarantine=(
            entry.status == EntryStatus.QUARANTINED
            and entry.quarantine_reason in {EMPTY_CONTENT_REASON, TOO_SHORT_CONTENT_REASON}
        ),
    )


@activity.defn
async def verify_entry_activity(entry_id: int) -> dict[str, Any]:
    TASKS_TOTAL.labels(type="verify_entry").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        summary = await session.scalar(select(Summary).where(Summary.entry_id == entry_id))
        if not entry or not summary:
            raise RuntimeError(f"Missing entry/summary for verify {entry_id}")

        citations = _extract_links(summary.summary_json)
        tavily = TavilyClient(settings)
        fallback_evidence = await tavily.search(f"{entry.title} {entry.url}", max_results=3)
        await tavily.close()

        client = DeepSeekClient(settings)
        try:
            output, usage = await client.verify(
                title=entry.title,
                url=entry.url,
                content_text=entry.content_text or "",
                summary_json=summary.summary_json,
                citations=citations,
                fallback_evidence=fallback_evidence,
            )
            await save_verification(session, entry_id, output, settings.llm_model_verify, usage)
            logger.info("Verification completed for entry %s", entry_id)
            return output.model_dump()
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)
            await set_verification_state(
                session,
                entry_id,
                VerificationState.FAILED,
                reason,
                error=f"verify failed: {reason}",
            )
            await set_process_outcome(session, entry_id, "failed", f"verify failed: {reason}")
            logger.warning("Verification failed for entry %s: %s", entry_id, exc)
            raise
        finally:
            await client.close()


@activity.defn
async def should_push_activity(entry_id: int) -> dict[str, bool | str] | bool:
    TASKS_TOTAL.labels(type="should_push").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        score = await get_score(session, entry_id)
        if entry is None or score is None:
            raise RuntimeError(f"Missing entry/score for push decision {entry_id}")
        if score.grade != Grade.A:
            await set_verification_state(
                session,
                entry_id,
                VerificationState.NOT_REQUIRED,
                PUSH_DECISION_REASON_NON_A,
            )
            await mark_entry_completed(session, entry_id, PROCESS_REASON_SCORED_NO_PUSH)
            logger.info(
                "Verification skipped for entry %s: %s",
                entry_id,
                PUSH_DECISION_REASON_NON_A,
            )
            logger.info("Process entry %s completed: %s", entry_id, PROCESS_REASON_SCORED_NO_PUSH)
            return {"eligible": False, "reason": PUSH_DECISION_REASON_NON_A}
        if not _is_within_push_window(
            entry, now=datetime.now(UTC), window_hours=settings.push_window_hours
        ):
            await set_verification_state(
                session,
                entry_id,
                VerificationState.NOT_REQUIRED,
                PUSH_DECISION_REASON_OUTSIDE_WINDOW,
            )
            await mark_entry_completed(session, entry_id, PROCESS_REASON_SCORED_NO_PUSH)
            logger.info(
                "Verification skipped for entry %s: %s",
                entry_id,
                PUSH_DECISION_REASON_OUTSIDE_WINDOW,
            )
            logger.info("Process entry %s completed: %s", entry_id, PROCESS_REASON_SCORED_NO_PUSH)
            return {"eligible": False, "reason": PUSH_DECISION_REASON_OUTSIDE_WINDOW}

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(Entry.id).where(
            Entry.updated_at >= today_start,
            Entry.status == EntryStatus.PUSHED,
        )
        pushed_today = len((await session.execute(stmt)).all())
        if pushed_today >= settings.a_push_limit_per_day:
            await set_verification_state(
                session,
                entry_id,
                VerificationState.NOT_REQUIRED,
                PUSH_DECISION_REASON_DAILY_CAP,
            )
            await mark_entry_completed(session, entry_id, PROCESS_REASON_SCORED_NO_PUSH)
            logger.info(
                "Verification skipped for entry %s: %s",
                entry_id,
                PUSH_DECISION_REASON_DAILY_CAP,
            )
            logger.info("Process entry %s completed: %s", entry_id, PROCESS_REASON_SCORED_NO_PUSH)
            return {"eligible": False, "reason": PUSH_DECISION_REASON_DAILY_CAP}

        await set_verification_state(
            session,
            entry_id,
            VerificationState.PENDING,
            PUSH_DECISION_REASON_ELIGIBLE,
        )
        logger.info("Verification pending for entry %s", entry_id)
        return {"eligible": True, "reason": PUSH_DECISION_REASON_ELIGIBLE}


@activity.defn
async def send_alert_activity(entry_id: int) -> None:
    TASKS_TOTAL.labels(type="send_alert").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        summary = await session.scalar(select(Summary).where(Summary.entry_id == entry_id))
        score = await get_score(session, entry_id)
        verification = await session.scalar(
            select(Verification).where(Verification.entry_id == entry_id)
        )
        if not entry or not summary or not score:
            raise RuntimeError(f"Missing data for alert {entry_id}")

        verification_line = "未核验"
        if verification is not None:
            verification_line = "核验已完成"

        body = (
            f"【{score.grade.value}】{entry.title}\n"
            f"- {summary.tldr}\n"
            f"评分：{score.grade.value} | Overall: {score.overall:.2f}\n"
            f"核验：{verification_line}\n"
            f"链接：{entry.url}\n"
            f"ID：E{entry.id}"
        )

        tg = TelegramClient(settings.telegram_bot_token)
        try:
            message_ids = await tg.send_markdown(settings.telegram_target_chat_id, body)
        except Exception as exc:  # noqa: BLE001
            await set_process_outcome(session, entry_id, "failed", f"push failed: {exc}")
            logger.warning("Process entry %s failed: push failed: %s", entry_id, exc)
            raise
        finally:
            await tg.close()

        await create_push_event(
            session,
            entry_id=entry_id,
            push_type=PushType.ALERT,
            telegram_chat_id=settings.telegram_target_chat_id,
            payload={"message": body},
            status=PushStatus.SENT,
            telegram_message_id=message_ids[-1] if message_ids else None,
        )
        await mark_entry_pushed(session, entry_id)
        logger.info("Process entry %s completed: %s", entry_id, "pushed")


def _extract_links(summary_json: dict[str, object]) -> list[dict[str, str]]:
    entities = summary_json.get("entities", {})
    if not isinstance(entities, dict):
        return []
    papers = entities.get("papers", [])
    if not isinstance(papers, list):
        return []

    links: list[dict[str, str]] = []
    for item in papers:
        if isinstance(item, dict):
            title = str(item.get("title", ""))
            url = str(item.get("url", ""))
            if url:
                links.append({"title": title, "url": url})
    return links


@activity.defn
async def build_digest_activity() -> dict[str, Any]:
    TASKS_TOTAL.labels(type="build_digest").inc()
    async with SessionFactory() as session:
        latest = await get_latest_report(session)
        window_start = latest.window_end if latest else datetime.now(UTC) - timedelta(days=1)
        window_end = datetime.now(UTC)

        stmt = (
            select(Entry, Score)
            .join(Score, Score.entry_id == Entry.id)
            .where(Entry.published_at >= window_start, Entry.published_at < window_end)
            .order_by(Score.overall.desc())
            .limit(30)
        )
        rows = (await session.execute(stmt)).all()

        top_items = [
            {
                "entry_id": int(entry.id),
                "title": entry.title,
                "url": entry.url,
                "why_important": score.rationale,
            }
            for entry, score in rows[:5]
        ]
        report_json = {
            "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
            "top_items": top_items,
            "clusters": [],
            "trend_radar": [],
            "action_recommendations": [],
        }
        markdown = _render_digest_markdown(report_json)

        report_id = await save_daily_report(session, window_start, window_end, markdown, report_json)
        return {"report_id": report_id, "markdown": markdown}


def _render_digest_markdown(report_json: dict[str, object]) -> str:
    window = report_json.get("window", {})
    top_items = report_json.get("top_items", [])
    lines = [
        f"📌 日报（窗口：{window.get('start')} ~ {window.get('end')}）",
        "",
        "Top 5:",
    ]
    for idx, item in enumerate(top_items, start=1):
        if isinstance(item, dict):
            lines.append(
                f"{idx}. {item.get('title')}（ID: E{item.get('entry_id')}）\\n{item.get('why_important')}\\n{item.get('url')}"
            )
    return "\n".join(lines)


@activity.defn
async def send_digest_activity(markdown: str) -> None:
    TASKS_TOTAL.labels(type="send_digest").inc()
    tg = TelegramClient(settings.telegram_bot_token)
    try:
        await tg.send_markdown(settings.telegram_target_chat_id, markdown)
    finally:
        await tg.close()


@activity.defn
async def generate_chat_answer_activity(question: str) -> dict[str, Any]:
    TASKS_TOTAL.labels(type="generate_chat_answer").inc()
    async with SessionFactory() as session:
        rows = await query_for_rag(session, question, limit=5)
        context = [
            {"entry_id": item[0], "title": item[1], "url": item[2], "summary": item[3]}
            for item in rows
        ]

    client = DeepSeekClient(settings)
    try:
        output = await client.chat_answer(question, context)
    finally:
        await client.close()

    return output.model_dump()


@activity.defn
async def deepdive_activity(entry_id: int, requestor_chat_id: int) -> None:
    TASKS_TOTAL.labels(type="deepdive").inc()
    verification = await verify_entry_activity(entry_id)
    verdict = verification.get("verdict", VerificationVerdict.UNCERTAIN.value)

    text = (
        f"DeepDive 结果（E{entry_id}）\n"
        f"核验结论：{verdict}\n"
        f"说明：{verification.get('notes', '')}"
    )

    tg = TelegramClient(settings.telegram_bot_token)
    try:
        await tg.send_markdown(requestor_chat_id, text)
    finally:
        await tg.close()
