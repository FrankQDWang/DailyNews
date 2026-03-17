from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from libs.core.db.repositories import upsert_entry


class _FakeRepoSession:
    def __init__(self, scalar_results: list[object]) -> None:
        self._scalar_results = iter(scalar_results)
        self.commit_calls = 0

    async def scalar(self, _: object) -> object:
        return next(self._scalar_results)

    async def commit(self) -> None:
        self.commit_calls += 1


async def test_upsert_entry_reuses_existing_row_for_duplicate_url() -> None:
    existing_entry = SimpleNamespace(
        id=7,
        miniflux_entry_id=10,
        miniflux_feed_id=1,
        url="https://example.com/post",
        title="Old title",
        author="Old author",
        published_at=datetime(2026, 3, 16, 0, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 3, 16, 1, 0, tzinfo=UTC),
        content_html="old html",
        content_text="old text",
        updated_at=datetime(2026, 3, 16, 2, 0, tzinfo=UTC),
    )
    session = _FakeRepoSession([None, existing_entry])

    entry_id = await upsert_entry(
        session,  # type: ignore[arg-type]
        miniflux_entry_id=99,
        miniflux_feed_id=5,
        url="https://example.com/post",
        title="New title",
        author="New author",
        published_at=datetime(2026, 3, 17, 0, 0, tzinfo=UTC),
        fetched_at=None,
        content_html=None,
        content_text=None,
    )

    assert entry_id == 7
    assert existing_entry.miniflux_entry_id == 99
    assert existing_entry.miniflux_feed_id == 5
    assert existing_entry.title == "New title"
    assert existing_entry.author == "New author"
    assert existing_entry.content_html == "old html"
    assert existing_entry.content_text == "old text"
    assert session.commit_calls == 1
