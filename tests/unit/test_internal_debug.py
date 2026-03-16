from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from libs.core.db.enums import EntryStatus, Grade, PushStatus, PushType, VerificationVerdict
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
                "summaries": 1,
                "scores": 1,
                "verifications": 1,
                "push_events": 1,
                "processed_telegram_updates": 2,
                "daily_reports": 1,
            },
            "recent_entries": [
                {
                    "id": 1,
                    "miniflux_entry_id": 101,
                    "title": "Entry 1",
                    "status": "scored",
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
                    "created_at": "2026-03-16T10:03:00+00:00",
                }
            ],
            "recent_scores": [
                {
                    "entry_id": 1,
                    "grade": "A",
                    "overall": 0.95,
                    "push_recommended": True,
                    "created_at": "2026-03-16T10:04:00+00:00",
                }
            ],
            "recent_verifications": [
                {
                    "entry_id": 1,
                    "verdict": "verified",
                    "confidence": 0.9,
                    "created_at": "2026-03-16T10:05:00+00:00",
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
        "recent_entries",
        "recent_summaries",
        "recent_scores",
        "recent_verifications",
        "recent_push_events",
        "recent_processed_updates",
    }
    assert isinstance(body["generated_at"], str)
    assert body["counts"]["processed_telegram_updates"] == 2
    assert body["recent_entries"][0]["status"] == "scored"


class _FakeScalarResult:
    def __init__(self, items: Sequence[object]) -> None:
        self._items = items

    def all(self) -> Sequence[object]:
        return self._items


class _FakeExecuteResult:
    def __init__(self, items: Sequence[object]) -> None:
        self._items = items

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._items)


class _FakeSession:
    def __init__(self, counts: list[int], result_sets: Sequence[Sequence[object]]) -> None:
        self._counts = iter(counts)
        self._result_sets = iter(result_sets)

    async def scalar(self, _: object) -> int:
        return next(self._counts)

    async def execute(self, _: object) -> _FakeExecuteResult:
        return _FakeExecuteResult(next(self._result_sets))


async def test_get_debug_overview_empty_snapshot() -> None:
    session = _FakeSession(
        counts=[0, 0, 0, 0, 0, 0, 0],
        result_sets=[[], [], [], [], [], []],
    )

    snapshot = await get_debug_overview(session)  # type: ignore[arg-type]
    dumped = snapshot.model_dump(mode="json")

    assert snapshot.counts.entries == 0
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
            created_at=base_time,
        )
    ]
    scores = [
        SimpleNamespace(
            entry_id=1,
            grade=Grade.A,
            overall=0.93,
            push_recommended=True,
            created_at=base_time + timedelta(minutes=1),
        )
    ]
    verifications = [
        SimpleNamespace(
            entry_id=1,
            verdict=VerificationVerdict.VERIFIED,
            confidence=0.84,
            created_at=base_time + timedelta(minutes=2),
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
    session = _FakeSession(
        counts=[6, 1, 1, 1, 1, 1, 1],
        result_sets=[
            entries,
            summaries,
            scores,
            verifications,
            push_events,
            processed_updates,
        ],
    )

    snapshot = await get_debug_overview(session)  # type: ignore[arg-type]
    dumped = snapshot.model_dump(mode="json")

    assert snapshot.counts.entries == 6
    assert len(snapshot.recent_entries) == 5
    assert snapshot.recent_entries[0].status == "scored"
    assert snapshot.recent_scores[0].grade == "A"
    assert snapshot.recent_verifications[0].verdict == "verified"
    assert snapshot.recent_push_events[0].status == "sent"
    assert snapshot.recent_processed_updates[0].update_id == 9001
    assert isinstance(dumped["recent_entries"][0]["created_at"], str)
