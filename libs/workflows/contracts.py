from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict


class IngestEntryResult(TypedDict):
    entry_id: int
    miniflux_entry_id: int
    published_at: str | None
    current_status: str
    needs_processing: bool
    should_mark_read: bool


type IngestActivityPayloadValue = str | int | bool | None
type IngestActivityResult = dict[str, IngestActivityPayloadValue] | int


class PushDecisionResult(TypedDict):
    eligible: bool
    reason: str


type PushDecisionPayloadValue = str | bool
type PushDecisionActivityResult = dict[str, PushDecisionPayloadValue] | bool


def ingest_result_entry_id(result: IngestActivityResult) -> int:
    if isinstance(result, int):
        return result
    return int(result["entry_id"])


def ingest_result_needs_processing(result: IngestActivityResult) -> bool:
    if isinstance(result, int):
        return True
    return bool(result["needs_processing"])


def ingest_result_should_mark_read(result: IngestActivityResult) -> bool:
    if isinstance(result, int):
        return False
    return bool(result.get("should_mark_read", False))


def is_ingest_result_mapping(value: object) -> bool:
    return isinstance(value, Mapping)


def push_decision_is_eligible(result: PushDecisionActivityResult) -> bool:
    if isinstance(result, bool):
        return result
    return bool(result["eligible"])


def push_decision_reason(result: PushDecisionActivityResult) -> str:
    if isinstance(result, bool):
        return "eligible_for_verification" if result else "non_a"
    return str(result["reason"])
