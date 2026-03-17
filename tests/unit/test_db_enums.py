from typing import cast

from sqlalchemy import Enum as SAEnum

from libs.core.db.models import Entry, PushEvent, UserFeedback, Verification


def test_db_enum_columns_use_database_values() -> None:
    entry_status = cast(SAEnum, Entry.__table__.c.status.type)
    verification_state = cast(SAEnum, Entry.__table__.c.verification_state.type)
    verification_verdict = cast(SAEnum, Verification.__table__.c.verdict.type)
    push_type = cast(SAEnum, PushEvent.__table__.c.type.type)
    push_status = cast(SAEnum, PushEvent.__table__.c.status.type)
    feedback_type = cast(SAEnum, UserFeedback.__table__.c.feedback.type)

    assert entry_status.enums == [
        "new",
        "summarized",
        "scored",
        "verified",
        "pushed",
        "quarantined",
        "failed",
    ]
    assert verification_verdict.enums == [
        "verified",
        "partially_verified",
        "uncertain",
    ]
    assert verification_state.enums == [
        "not_required",
        "pending",
        "verified",
        "failed",
        "legacy_gap",
    ]
    assert push_type.enums == ["alert", "digest", "reply"]
    assert push_status.enums == ["sent", "failed"]
    assert feedback_type.enums == [
        "up",
        "down",
        "save",
        "mute_source",
    ]
