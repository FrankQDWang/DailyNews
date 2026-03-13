from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EntryRef:
    entry_id: int


@dataclass(slots=True)
class PushInput:
    entry_id: int
    force: bool = False


@dataclass(slots=True)
class DigestInput:
    chat_id: int


@dataclass(slots=True)
class DeepDiveInput:
    entry_id: int
    requestor_chat_id: int
    requestor_user_id: int
