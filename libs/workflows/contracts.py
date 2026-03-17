from __future__ import annotations

from typing import TypedDict


class IngestEntryResult(TypedDict):
    entry_id: int
    miniflux_entry_id: int
    published_at: str | None
    current_status: str
    needs_processing: bool
