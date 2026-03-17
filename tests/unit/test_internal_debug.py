from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from libs.core.db.enums import (
    ContentFetchState,
    EntryStatus,
    Grade,
    PushStatus,
    PushType,
    VerificationVerdict,
)
from libs.core.db.repositories import get_debug_overview
from libs.core.schemas.debug import DebugOverviewResponse
from libs.core.settings import get_settings


def _base_env() -> dict[str, str]:
    return {
        "ASSISTANT_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
        "TEMPORAL_HOST": "localhost:7233",
        "DEEPSEEK_API_KEY": "x",
        "MINIFLUX_BASE_URL": "http://localhost:8080",
        "MINIFLUX_API_TOKEN": "x",
        "TELEGRAM_BOT_TOKEN": "x",
        "TELEGRAM_WEBHOOK_SECRET": "secret",
        "TELEGRAM_TARGET_CHAT_ID": "-10001",
        "TELEGRAM_ADMIN_USER_IDS": "[1, 2, 3]",
        "INTERNAL_API_TOKEN": "internal",
    }


def _load_app_module(monkeypatch: Any) -> Any:
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    for module_name in ("apps.api.main", "apps.api.dependencies", "libs.core.db.session"):
        sys.modules.pop(module_name, None)

    return importlib.import_module("apps.api.main")


def test_internal_debug_overview_requires_headers(monkeypatch: Any) -> None:
    main_module = _load_app_module(monkeypatch)

    async def override_get_session() -> Any:
        yield object()

    main_module.app.dependency_overrides[main_module.get_session] = override_get_session

    with TestClient(main_module.app) as client:
        response = client.get("/internal/debug/overview")

    main_module.app.dependency_overrides.clear()
    assert response.status_code == 422


def test_internal_debug_overview_rejects_invalid_internal_token(monkeypatch: Any) -> None:
    main_module = _load_app_module(monkeypatch)

    async def override_get_session() -> Any:
        yield object()

    main_module.app.dependency_overrides[main_module.get_session] = override_get_session

    with TestClient(main_module.app) as client:
        response = client.get(
            "/internal/debug/overview",
            headers={
                "x-internal-token": "wrong",
                "x-admin-user-id": "1",
            },
        )

    main_module.app.dependency_overrides.clear()
    assert response.status_code == 403
    assert response.json() == {"detail": "invalid internal token"}


def test_internal_debug_overview_rejects_non_admin(monkeypatch: Any) -> None:
    main_module = _load_app_module(monkeypatch)

    async def override_get_session() -> Any:
        yield object()

    main_module.app.dependency_overrides[main_module.get_session] = override_get_session

    with TestClient(main_module.app) as client:
        response = client.get(
            "/internal/debug/overview",
            headers={
                "x-internal-token": "internal",
                "x-admin-user-id": "99",
            },
        )

    main_module.app.dependency_overrides.clear()
    assert response.status_code == 403
    assert response.json() == {"detail": "not admin"}


def test_internal_debug_overview_returns_fixed_shape(monkeypatch: Any) -> None:
    main_module = _load_app_module(monkeypatch)
    snapshot = DebugOverviewResponse.model_validate(
        {
            "generated_at": "2026-03-16T12:00:00+00:00",
            "counts": {
                "entries": 1,
                "quarantined_entries": 0,
                "fetch_cooldown_entries": 1,
                "fetch_blocked_entries": 0,
                "too_short_entries": 0,
                "summaries": 1,
                "scores": 1,
                "verifications": 1,
                "verification_pending": 0,
                "verification_failed": 0,
                "verification_not_required": 1,
                "verification_legacy_gap": 0,
                "push_events": 1,
                "processed_telegram_updates": 2,
                "daily_reports": 1,
            },
            "llm_tokens_last_24h": {
                "summary": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                "score": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
                "verify": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
            "latest_ingest_batch": {
                "scanned_count": 300,
                "actionable_count": 30,
                "marked_read_count": 7,
                "skipped_terminal_count": 12,
                "skipped_cooldown_count": 4,
                "skipped_blocked_count": 3,
                "finished_at": "2026-03-16T10:08:00+00:00",
            },
            "recent_entries": [
                {
                    "id": 1,
                    "miniflux_entry_id": 101,
                    "title": "Entry 1",
                    "status": "scored",
                    "quarantine_reason": None,
                    "content_fetch_state": "ready",
                    "content_fetch_fail_count": 0,
                    "next_content_fetch_after": None,
                    "last_content_fetch_error": None,
                    "verification_state": "not_required",
                    "verification_reason": "non_a",
                    "verified_at": None,
                    "published_at": "2026-03-16T10:00:00+00:00",
                    "created_at": "2026-03-16T10:01:00+00:00",
                    "updated_at": "2026-03-16T10:02:00+00:00",
                    "error": None,
                }
            ],
            "recent_summaries": [
                {
                    "entry_id": 1,
                    "summary_confidence": 0.91,
                    "model": "deepseek-chat",
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "created_at": "2026-03-16T10:03:00+00:00",
                }
            ],
            "recent_scores": [
                {
                    "entry_id": 1,
                    "grade": "A",
                    "overall": 0.95,
                    "push_recommended": True,
                    "prompt_tokens": 5,
                    "completion_tokens": 6,
                    "total_tokens": 11,
                    "created_at": "2026-03-16T10:04:00+00:00",
                }
            ],
            "recent_verifications": [
                {
                    "entry_id": 1,
                    "verdict": "verified",
                    "confidence": 0.9,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "created_at": "2026-03-16T10:05:00+00:00",
                }
            ],
            "recent_verification_candidates": [
                {
                    "entry_id": 1,
                    "grade": "A",
                    "verification_state": "not_required",
                    "verification_reason": "non_a",
                    "published_at": "2026-03-16T10:00:00+00:00",
                }
            ],
            "recent_push_events": [
                {
                    "id": 11,
                    "entry_id": 1,
                    "type": "alert",
                    "status": "sent",
                    "telegram_chat_id": -10001,
                    "telegram_message_id": 99,
                    "created_at": "2026-03-16T10:06:00+00:00",
                    "error": None,
                }
            ],
            "recent_processed_updates": [
                {
                    "update_id": 501,
                    "created_at": "2026-03-16T10:07:00+00:00",
                }
            ],
        }
    )

    async def override_get_session() -> Any:
        yield object()

    async def fake_get_debug_overview(_: Any) -> DebugOverviewResponse:
        return snapshot

    main_module.app.dependency_overrides[main_module.get_session] = override_get_session
    monkeypatch.setattr(main_module, "get_debug_overview", fake_get_debug_overview)

    with TestClient(main_module.app) as client:
        response = client.get(
            "/internal/debug/overview",
            headers={
                "x-internal-token": "internal",
                "x-admin-user-id": "1",
            },
        )

    main_module.app.dependency_overrides.clear()
    body = response.json()
    assert response.status_code == 200
    assert set(body) == {
        "generated_at",
        "counts",
        "llm_tokens_last_24h",
        "latest_ingest_batch",
        "recent_entries",
        "recent_summaries",
        "recent_scores",
        "recent_verifications",
        "recent_verification_candidates",
        "recent_push_events",
        "recent_processed_updates",
    }
    assert isinstance(body["generated_at"], str)
    assert body["counts"]["fetch_cooldown_entries"] == 1
    assert body["counts"]["verification_not_required"] == 1
    assert body["llm_tokens_last_24h"]["summary"]["total_tokens"] == 30
    assert body["latest_ingest_batch"]["actionable_count"] == 30
    assert body["recent_entries"][0]["content_fetch_state"] == "ready"


class _FakeScalarResult:
    def __init__(self, items: Sequence[object]) -> None:
        self._items = items

    def all(self) -> Sequence[object]:
        return self._items


class _FakeExecuteResult:
    def __init__(self, items: Sequence[object] | None = None, row: tuple[object, ...] | None = None) -> None:
        self._items = list(items or [])
        self._row = row

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._items)

    def all(self) -> Sequence[object]:
        return self._items

    def one(self) -> tuple[object, ...]:
        if self._row is None:
            raise AssertionError("expected one() row")
        return self._row


class _FakeSession:
    def __init__(self, counts: Sequence[object], execute_results: Sequence[_FakeExecuteResult]) -> None:
        self._counts = iter(counts)
        self._execute_results = iter(execute_results)

    async def scalar(self, _: object) -> object:
        return next(self._counts)

    async def execute(self, _: object) -> _FakeExecuteResult:
        return next(self._execute_results)


async def test_get_debug_overview_empty_snapshot() -> None:
    session = _FakeSession(
        counts=[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, None],
        execute_results=[
            _FakeExecuteResult(row=(0, 0, 0)),
            _FakeExecuteResult(row=(0, 0, 0)),
            _FakeExecuteResult(row=(0, 0, 0)),
            _FakeExecuteResult(items=[]),
            _FakeExecuteResult(items=[]),
            _FakeExecuteResult(items=[]),
            _FakeExecuteResult(items=[]),
            _FakeExecuteResult(items=[]),
            _FakeExecuteResult(items=[]),
            _FakeExecuteResult(items=[]),
        ],
    )

    snapshot = await get_debug_overview(session)  # type: ignore[arg-type]
    dumped = snapshot.model_dump(mode="json")

    assert snapshot.counts.entries == 0
    assert snapshot.counts.fetch_cooldown_entries == 0
    assert snapshot.llm_tokens_last_24h.summary.total_tokens == 0
    assert snapshot.latest_ingest_batch is None
    assert snapshot.recent_entries == []
    assert snapshot.recent_scores == []
    assert snapshot.recent_push_events == []
    assert isinstance(dumped["generated_at"], str)


async def test_get_debug_overview_maps_rows_and_limits_recent_entries() -> None:
    base_time = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    entries = [
        SimpleNamespace(
            id=index,
            miniflux_entry_id=1000 + index,
            title=f"Entry {index}",
            status=EntryStatus.SCORED,
            quarantine_reason=None,
            content_fetch_state=ContentFetchState.READY,
            content_fetch_fail_count=0,
            next_content_fetch_after=None,
            last_content_fetch_error=None,
            verification_state=None,
            verification_reason=None,
            verified_at=None,
            published_at=base_time - timedelta(minutes=index),
            created_at=base_time - timedelta(minutes=index),
            updated_at=base_time - timedelta(minutes=index - 1),
            error=None,
        )
        for index in range(6)
    ]
    summaries = [
        SimpleNamespace(
            entry_id=1,
            summary_confidence=0.88,
            model="deepseek-chat",
            prompt_tokens=20,
            completion_tokens=30,
            total_tokens=50,
            created_at=base_time,
        )
    ]
    scores = [
        SimpleNamespace(
            entry_id=1,
            grade=Grade.A,
            overall=0.93,
            push_recommended=True,
            prompt_tokens=10,
            completion_tokens=11,
            total_tokens=21,
            created_at=base_time + timedelta(minutes=1),
        )
    ]
    verifications = [
        SimpleNamespace(
            entry_id=1,
            verdict=VerificationVerdict.VERIFIED,
            confidence=0.84,
            prompt_tokens=5,
            completion_tokens=6,
            total_tokens=11,
            created_at=base_time + timedelta(minutes=2),
        )
    ]
    verification_candidates = [
        (
            SimpleNamespace(
                id=1,
                published_at=base_time - timedelta(minutes=1),
                verification_state=None,
                verification_reason="eligible_for_verification",
            ),
            SimpleNamespace(
                entry_id=1,
                grade=Grade.A,
            ),
        )
    ]
    push_events = [
        SimpleNamespace(
            id=88,
            entry_id=1,
            type=PushType.ALERT,
            status=PushStatus.SENT,
            telegram_chat_id=-10001,
            telegram_message_id=501,
            created_at=base_time + timedelta(minutes=3),
            error=None,
        )
    ]
    processed_updates = [
        SimpleNamespace(
            update_id=9001,
            created_at=base_time + timedelta(minutes=4),
        )
    ]
    latest_ingest_batch = SimpleNamespace(
        scanned_count=300,
        actionable_count=30,
        marked_read_count=9,
        skipped_terminal_count=12,
        skipped_cooldown_count=4,
        skipped_blocked_count=3,
        finished_at=base_time + timedelta(minutes=5),
    )
    session = _FakeSession(
        counts=[6, 0, 1, 0, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, latest_ingest_batch],
        execute_results=[
            _FakeExecuteResult(row=(20, 30, 50)),
            _FakeExecuteResult(row=(10, 11, 21)),
            _FakeExecuteResult(row=(5, 6, 11)),
            _FakeExecuteResult(items=entries),
            _FakeExecuteResult(items=summaries),
            _FakeExecuteResult(items=scores),
            _FakeExecuteResult(items=verifications),
            _FakeExecuteResult(items=verification_candidates),
            _FakeExecuteResult(items=push_events),
            _FakeExecuteResult(items=processed_updates),
        ],
    )

    snapshot = await get_debug_overview(session)  # type: ignore[arg-type]
    dumped = snapshot.model_dump(mode="json")

    assert snapshot.counts.entries == 6
    assert snapshot.counts.fetch_cooldown_entries == 1
    assert snapshot.counts.too_short_entries == 1
    assert snapshot.counts.verification_not_required == 1
    assert snapshot.llm_tokens_last_24h.summary.total_tokens == 50
    assert snapshot.latest_ingest_batch is not None
    assert snapshot.latest_ingest_batch.marked_read_count == 9
    assert len(snapshot.recent_entries) == 5
    assert snapshot.recent_entries[0].content_fetch_state == "ready"
    assert snapshot.recent_scores[0].grade == "A"
    assert snapshot.recent_verifications[0].verdict == "verified"
    assert snapshot.recent_verification_candidates[0].grade == "A"
    assert snapshot.recent_push_events[0].status == "sent"
    assert snapshot.recent_processed_updates[0].update_id == 9001
    assert isinstance(dumped["recent_entries"][0]["created_at"], str)
