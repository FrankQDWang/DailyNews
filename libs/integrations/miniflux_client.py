from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import httpx

from libs.core.settings import Settings


@dataclass(slots=True)
class MinifluxEntry:
    id: int
    feed_id: int | None
    title: str
    url: str
    author: str | None
    published_at: datetime | None
    content: str | None


class MinifluxClient:
    def __init__(self, settings: Settings) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.miniflux_base_url,
            headers={"X-Auth-Token": settings.miniflux_api_token},
            timeout=30,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def refresh_feeds(self) -> None:
        resp = await self._client.put("/v1/feeds/refresh")
        resp.raise_for_status()

    async def list_unread_entries(self, limit: int = 100) -> list[MinifluxEntry]:
        resp = await self._client.get(
            "/v1/entries", params={"status": "unread", "direction": "desc", "limit": limit}
        )
        resp.raise_for_status()
        rows = resp.json().get("entries", [])
        return [_parse_entry(row) for row in rows]

    async def fetch_content(self, entry_id: int) -> MinifluxEntry:
        resp = await self._client.get(
            f"/v1/entries/{entry_id}/fetch-content", params={"update_content": "true"}
        )
        resp.raise_for_status()
        data = resp.json().get("entry", resp.json())
        return _parse_entry(data)


def serialize_entries(entries: list[MinifluxEntry]) -> list[dict[str, object]]:
    return [asdict(entry) for entry in entries]


def _parse_entry(data: dict[str, object]) -> MinifluxEntry:
    published_raw = data.get("date") or data.get("published_at")
    published_at: datetime | None = None
    if isinstance(published_raw, str):
        published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00")).astimezone(UTC)

    return MinifluxEntry(
        id=int(data["id"]),
        feed_id=int(data["feed_id"]) if data.get("feed_id") is not None else None,
        title=str(data.get("title", "")),
        url=str(data.get("url", "")),
        author=str(data["author"]) if data.get("author") else None,
        published_at=published_at,
        content=str(data["content"]) if data.get("content") else None,
    )
