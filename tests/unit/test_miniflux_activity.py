from __future__ import annotations

from datetime import UTC, datetime

from libs.integrations.miniflux_client import MinifluxEntry, serialize_entries


def test_serialize_entries_from_dataclass() -> None:
    rows = serialize_entries(
        [
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
    )

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
