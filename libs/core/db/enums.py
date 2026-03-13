from __future__ import annotations

from enum import Enum


class EntryStatus(str, Enum):
    NEW = "new"
    SUMMARIZED = "summarized"
    SCORED = "scored"
    VERIFIED = "verified"
    PUSHED = "pushed"
    FAILED = "failed"


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class VerificationVerdict(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNCERTAIN = "uncertain"


class PushType(str, Enum):
    ALERT = "alert"
    DIGEST = "digest"
    REPLY = "reply"


class PushStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"


class FeedbackType(str, Enum):
    UP = "up"
    DOWN = "down"
    SAVE = "save"
    MUTE_SOURCE = "mute_source"
