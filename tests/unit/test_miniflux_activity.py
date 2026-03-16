from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from pytest import MonkeyPatch

from libs.integrations.miniflux_client import MinifluxEntry
from libs.workflows import activities


class _FakeMinifluxClient:
    def __init__(self, settings: object) -> None:
        del settings

    async def list_unread_entries(self, limit: int = 100) -> list[MinifluxEntry]:
        del limit
        return [
            MinifluxEntry(
                id=123,
                feed_id=9,
                title="Test entry",
                url="https://example.com/post",
                author="Tester",
                published_at=datetime(2026, 3, 16, 3, 0, tzinfo=UTC),
                content="hello",
            )
        ]

    async def close(self) -> None:
        return None


def test_list_unread_miniflux_activity_serializes_dataclass(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(activities, "MinifluxClient", _FakeMinifluxClient)

    rows = asyncio.run(activities.list_unread_miniflux_activity(limit=1))

    assert rows == [
        {
            "id": 123,
            "feed_id": 9,
            "title": "Test entry",
            "url": "https://example.com/post",
            "author": "Tester",
            "published_at": datetime(2026, 3, 16, 3, 0, tzinfo=UTC),
            "content": "hello",
        }
    ]
