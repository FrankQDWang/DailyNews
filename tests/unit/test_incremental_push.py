from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx

from libs.core.db.enums import EntryStatus, Grade
from libs.core.settings import Settings, get_settings
from libs.integrations.miniflux_client import MinifluxClient, MinifluxEntry, MinifluxEntryPayload
from libs.workflows.contracts import ingest_result_entry_id, ingest_result_needs_processing


def _base_env() -> dict[str, str]:
    return {
        "ASSISTANT_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
        "TEMPORAL_HOST": "localhost:7233",
        "DEEPSEEK_API_KEY": "x",
        "MINIFLUX_BASE_URL": "https://example.com",
        "MINIFLUX_API_TOKEN": "token",
        "TELEGRAM_BOT_TOKEN": "x",
        "TELEGRAM_WEBHOOK_SECRET": "secret",
        "TELEGRAM_TARGET_CHAT_ID": "-10001",
        "TELEGRAM_ADMIN_USER_IDS": "[1, 2, 3]",
        "INTERNAL_API_TOKEN": "internal",
    }


class _SessionContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc_type, exc, tb
        return False


class _FakeExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeSession:
    def __init__(self, pushed_today: int = 0) -> None:
        self._pushed_today = pushed_today

    async def execute(self, _: object) -> _FakeExecuteResult:
        return _FakeExecuteResult([object()] * self._pushed_today)


def _load_activities_module(monkeypatch: Any) -> Any:
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    for module_name in ("libs.workflows.activities", "libs.core.db.session"):
        sys.modules.pop(module_name, None)

    return importlib.import_module("libs.workflows.activities")


async def test_miniflux_mark_entries_read_uses_bulk_endpoint() -> None:
    seen: dict[str, Any] = {}
    env = _base_env()
    env["TELEGRAM_ADMIN_USER_IDS"] = "1,2,3"

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(status_code=204)

    client = MinifluxClient(Settings.model_validate(env))
    await client.close()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    )

    try:
        await client.mark_entries_read([11, 22])
    finally:
        await client.close()

    assert seen == {
        "method": "PUT",
        "path": "/v1/entries",
        "body": '{"entry_ids":[11,22],"status":"read"}',
    }


async def test_fetch_and_upsert_entry_activity_returns_terminal_entry_contract(monkeypatch: Any) -> None:
    activities = _load_activities_module(monkeypatch)
    payload: MinifluxEntryPayload = {
        "id": 123,
        "feed_id": 9,
        "title": "Entry",
        "url": "https://example.com/post",
        "author": "Tester",
        "published_at": "2026-03-17T00:00:00+00:00",
        "content": "body",
    }
    fetched_entry = MinifluxEntry(
        id=123,
        feed_id=9,
        title="Entry",
        url="https://example.com/post",
        author="Tester",
        published_at=datetime(2026, 3, 17, 0, 0, tzinfo=UTC),
        content="body",
    )

    class _FakeMinifluxClient:
        async def fetch_content(self, _: int) -> MinifluxEntry:
            return fetched_entry

        async def close(self) -> None:
            return None

    async def fake_upsert_entry(_: object, **__: object) -> int:
        return 42

    async def fake_get_entry_for_processing(_: object, __: int) -> object:
        return SimpleNamespace(
            id=42,
            miniflux_entry_id=123,
            published_at=datetime(2026, 3, 17, 0, 0, tzinfo=UTC),
            status=EntryStatus.SCORED,
        )

    monkeypatch.setattr(activities, "MinifluxClient", lambda _: _FakeMinifluxClient())
    monkeypatch.setattr(activities, "SessionFactory", lambda: _SessionContext(object()))
    monkeypatch.setattr(activities, "upsert_entry", fake_upsert_entry)
    monkeypatch.setattr(activities, "get_entry_for_processing", fake_get_entry_for_processing)

    result = await activities.fetch_and_upsert_entry_activity(payload)

    assert result == {
        "entry_id": 42,
        "miniflux_entry_id": 123,
        "published_at": "2026-03-17T00:00:00+00:00",
        "current_status": "scored",
        "needs_processing": False,
    }


async def test_fetch_and_upsert_entry_activity_quarantines_empty_content(monkeypatch: Any) -> None:
    activities = _load_activities_module(monkeypatch)
    payload: MinifluxEntryPayload = {
        "id": 123,
        "feed_id": 9,
        "title": "Entry",
        "url": "https://example.com/post",
        "author": "Tester",
        "published_at": "2026-03-17T00:00:00+00:00",
        "content": "<p></p>",
    }
    fetched_entry = MinifluxEntry(
        id=123,
        feed_id=9,
        title="Entry",
        url="https://example.com/post",
        author="Tester",
        published_at=datetime(2026, 3, 17, 0, 0, tzinfo=UTC),
        content="<p></p>",
    )

    class _FakeMinifluxClient:
        async def fetch_content(self, _: int) -> MinifluxEntry:
            return fetched_entry

        async def close(self) -> None:
            return None

    entry_states = [
        SimpleNamespace(
            id=42,
            miniflux_entry_id=123,
            published_at=datetime(2026, 3, 17, 0, 0, tzinfo=UTC),
            status=EntryStatus.FAILED,
            quarantine_reason=None,
        ),
        SimpleNamespace(
            id=42,
            miniflux_entry_id=123,
            published_at=datetime(2026, 3, 17, 0, 0, tzinfo=UTC),
            status=EntryStatus.QUARANTINED,
            quarantine_reason="empty_content",
        ),
    ]
    quarantined: list[tuple[int, str]] = []

    async def fake_upsert_entry(_: object, **__: object) -> int:
        return 42

    async def fake_get_entry_for_processing(_: object, __: int) -> object:
        return entry_states.pop(0)

    async def fake_quarantine_entry(_: object, entry_id: int, reason: str) -> None:
        quarantined.append((entry_id, reason))

    monkeypatch.setattr(activities, "MinifluxClient", lambda _: _FakeMinifluxClient())
    monkeypatch.setattr(activities, "SessionFactory", lambda: _SessionContext(object()))
    monkeypatch.setattr(activities, "upsert_entry", fake_upsert_entry)
    monkeypatch.setattr(activities, "get_entry_for_processing", fake_get_entry_for_processing)
    monkeypatch.setattr(activities, "quarantine_entry", fake_quarantine_entry)

    result = await activities.fetch_and_upsert_entry_activity(payload)

    assert quarantined == [(42, "empty_content")]
    assert result == {
        "entry_id": 42,
        "miniflux_entry_id": 123,
        "published_at": "2026-03-17T00:00:00+00:00",
        "current_status": "quarantined",
        "needs_processing": False,
    }


def test_empty_content_normalization_handles_blank_html(monkeypatch: Any) -> None:
    activities = _load_activities_module(monkeypatch)
    assert activities._is_empty_content("<p>&nbsp;</p>\u200b")
    assert not activities._is_empty_content("<p>Hello</p>")


async def test_should_push_activity_rejects_historical_entries(monkeypatch: Any) -> None:
    activities = _load_activities_module(monkeypatch)
    now = datetime.now(UTC)
    entry = SimpleNamespace(
        id=1,
        published_at=now - timedelta(hours=25),
        created_at=now - timedelta(hours=25),
        status=EntryStatus.SCORED,
    )
    score = SimpleNamespace(grade=Grade.A)
    session = _FakeSession(pushed_today=0)

    async def fake_get_entry_for_processing(_: object, __: int) -> object:
        return entry

    async def fake_get_score(_: object, __: int) -> object:
        return score

    monkeypatch.setattr(activities, "SessionFactory", lambda: _SessionContext(session))
    monkeypatch.setattr(activities, "get_entry_for_processing", fake_get_entry_for_processing)
    monkeypatch.setattr(activities, "get_score", fake_get_score)
    monkeypatch.setattr(activities.settings, "push_window_hours", 24)

    result = await activities.should_push_activity(1)

    assert result is False


async def test_should_push_activity_uses_created_at_fallback(monkeypatch: Any) -> None:
    activities = _load_activities_module(monkeypatch)
    now = datetime.now(UTC)
    entry = SimpleNamespace(
        id=1,
        published_at=None,
        created_at=now - timedelta(hours=2),
        status=EntryStatus.SCORED,
    )
    score = SimpleNamespace(grade=Grade.A)
    session = _FakeSession(pushed_today=0)

    async def fake_get_entry_for_processing(_: object, __: int) -> object:
        return entry

    async def fake_get_score(_: object, __: int) -> object:
        return score

    monkeypatch.setattr(activities, "SessionFactory", lambda: _SessionContext(session))
    monkeypatch.setattr(activities, "get_entry_for_processing", fake_get_entry_for_processing)
    monkeypatch.setattr(activities, "get_score", fake_get_score)
    monkeypatch.setattr(activities.settings, "push_window_hours", 24)
    monkeypatch.setattr(activities.settings, "a_push_limit_per_day", 10)

    result = await activities.should_push_activity(1)

    assert result is True


async def test_mark_entry_read_activity_returns_false_when_miniflux_fails(monkeypatch: Any) -> None:
    activities = _load_activities_module(monkeypatch)
    session = object()
    entry = SimpleNamespace(
        id=7,
        miniflux_entry_id=701,
        status=EntryStatus.SCORED,
        quarantine_reason=None,
    )

    class _FailingMinifluxClient:
        async def mark_entries_read(self, _: list[int]) -> None:
            raise httpx.HTTPError("boom")

        async def close(self) -> None:
            return None

    async def fake_get_entry_for_processing(_: object, __: int) -> object:
        return entry

    monkeypatch.setattr(activities, "SessionFactory", lambda: _SessionContext(session))
    monkeypatch.setattr(activities, "get_entry_for_processing", fake_get_entry_for_processing)
    monkeypatch.setattr(activities, "MinifluxClient", lambda _: _FailingMinifluxClient())

    assert await activities.mark_entry_read_activity(7) is False


async def test_summarize_entry_activity_quarantines_empty_content(monkeypatch: Any) -> None:
    activities = _load_activities_module(monkeypatch)
    session = object()
    entry = SimpleNamespace(id=7, miniflux_entry_id=701, content_text="<p></p>")
    quarantined: list[tuple[int, str]] = []
    read_sync_calls: list[tuple[int, bool]] = []

    async def fake_get_entry_for_processing(_: object, __: int) -> object:
        return entry

    async def fake_quarantine_entry(_: object, entry_id: int, reason: str) -> None:
        quarantined.append((entry_id, reason))

    async def fake_sync_miniflux_read_for_entry(entry_obj: Any, *, after_quarantine: bool) -> bool:
        read_sync_calls.append((entry_obj.id, after_quarantine))
        return True

    monkeypatch.setattr(activities, "SessionFactory", lambda: _SessionContext(session))
    monkeypatch.setattr(activities, "get_entry_for_processing", fake_get_entry_for_processing)
    monkeypatch.setattr(activities, "quarantine_entry", fake_quarantine_entry)
    monkeypatch.setattr(activities, "_sync_miniflux_read_for_entry", fake_sync_miniflux_read_for_entry)

    try:
        await activities.summarize_entry_activity(7)
    except RuntimeError as exc:
        assert "quarantined due to empty content" in str(exc)
    else:
        raise AssertionError("expected summarize_entry_activity to raise for empty content")

    assert quarantined == [(7, "empty_content")]
    assert read_sync_calls == [(7, True)]


def test_ingest_result_helpers_accept_legacy_int_payload() -> None:
    assert ingest_result_entry_id(42) == 42
    assert ingest_result_needs_processing(42) is True
