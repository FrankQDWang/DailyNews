from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict


class IngestEntryResult(TypedDict):
    entry_id: int
    miniflux_entry_id: int
    published_at: str | None
    current_status: str
    needs_processing: bool


type IngestActivityPayloadValue = str | int | bool | None
type IngestActivityResult = dict[str, IngestActivityPayloadValue] | int


def ingest_result_entry_id(result: IngestActivityResult) -> int:
    if isinstance(result, int):
        return result
    return int(result["entry_id"])


def ingest_result_needs_processing(result: IngestActivityResult) -> bool:
    if isinstance(result, int):
        return True
    return bool(result["needs_processing"])


def is_ingest_result_mapping(value: object) -> bool:
    return isinstance(value, Mapping)
