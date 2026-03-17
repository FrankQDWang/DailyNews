from __future__ import annotations

from datetime import UTC, datetime

import httpx

from libs.core.settings import Settings
from libs.integrations.miniflux_client import MinifluxClient, MinifluxEntry, serialize_entries


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
            "published_at": "2026-03-16T03:00:00+00:00",
            "content": "hello",
        }
    ]


async def test_fetch_content_accepts_content_only_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/entries/962/fetch-content"
        return httpx.Response(
            status_code=200,
            json={"content": "<p>body</p>", "reading_time": 6},
            request=request,
        )

    settings = Settings.model_validate(
        {
            "ASSISTANT_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
            "TEMPORAL_HOST": "localhost:7233",
            "DEEPSEEK_API_KEY": "x",
            "MINIFLUX_BASE_URL": "https://example.com",
            "MINIFLUX_API_TOKEN": "token",
            "TELEGRAM_BOT_TOKEN": "x",
            "TELEGRAM_WEBHOOK_SECRET": "secret",
            "TELEGRAM_TARGET_CHAT_ID": "-10001",
            "TELEGRAM_ADMIN_USER_IDS": "1,2,3",
            "INTERNAL_API_TOKEN": "internal",
        }
    )
    client = MinifluxClient(settings)
    await client.close()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    )

    try:
        entry = await client.fetch_content(962)
    finally:
        await client.close()

    assert entry.id == 962
    assert entry.content == "<p>body</p>"
    assert entry.feed_id is None
    assert entry.title == ""
    assert entry.url == ""
