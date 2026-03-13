from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from libs.core.db.enums import EntryStatus, Grade, PushStatus, PushType
from libs.core.db.models import (
    DailyReport,
    Entry,
    ProcessedTelegramUpdate,
    PushEvent,
    Score,
    Summary,
    Verification,
)
from libs.core.schemas.llm import L0SummaryOutput, L1ScoreOutput, L2VerifyOutput


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def upsert_entry(
    session: AsyncSession,
    *,
    miniflux_entry_id: int,
    miniflux_feed_id: int | None,
    url: str,
    title: str,
    author: str | None,
    published_at: datetime | None,
    fetched_at: datetime | None,
    content_html: str | None,
    content_text: str | None,
) -> int:
    stmt = pg_insert(Entry).values(
        miniflux_entry_id=miniflux_entry_id,
        miniflux_feed_id=miniflux_feed_id,
        url=url,
        title=title,
        author=author,
        published_at=published_at,
        fetched_at=fetched_at,
        content_html=content_html,
        content_text=content_text,
        status=EntryStatus.NEW,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Entry.miniflux_entry_id],
        set_={
            "title": title,
            "author": author,
            "published_at": published_at,
            "fetched_at": fetched_at,
            "content_html": content_html,
            "content_text": content_text,
            "updated_at": func.now(),
        },
    ).returning(Entry.id)
    entry_id = await session.scalar(stmt)
    await session.commit()
    if entry_id is None:
        raise RuntimeError("Failed to upsert entry")
    return int(entry_id)


async def mark_entry_failed(session: AsyncSession, entry_id: int, error: str) -> None:
    await session.execute(
        update(Entry).where(Entry.id == entry_id).values(status=EntryStatus.FAILED, error=error)
    )
    await session.commit()


async def save_summary(session: AsyncSession, entry_id: int, output: L0SummaryOutput, model: str) -> None:
    stmt = pg_insert(Summary).values(
        entry_id=entry_id,
        tldr=output.tldr,
        key_points=[point.model_dump() for point in output.key_points],
        ai_pm_takeaways=[takeaway.model_dump() for takeaway in output.ai_pm_takeaways],
        tags=output.tags,
        entities=output.entities.model_dump(),
        risk_flags=output.risk_flags,
        action_items=[item.model_dump() for item in output.ai_pm_takeaways],
        claims=[claim.model_dump() for claim in output.claims],
        summary_confidence=output.summary_confidence,
        summary_json=output.model_dump(),
        model=model,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Summary.entry_id],
        set_={
            "tldr": output.tldr,
            "key_points": [point.model_dump() for point in output.key_points],
            "ai_pm_takeaways": [takeaway.model_dump() for takeaway in output.ai_pm_takeaways],
            "tags": output.tags,
            "entities": output.entities.model_dump(),
            "risk_flags": output.risk_flags,
            "action_items": [item.model_dump() for item in output.ai_pm_takeaways],
            "claims": [claim.model_dump() for claim in output.claims],
            "summary_confidence": output.summary_confidence,
            "summary_json": output.model_dump(),
            "model": model,
        },
    )
    await session.execute(stmt)
    await session.execute(update(Entry).where(Entry.id == entry_id).values(status=EntryStatus.SUMMARIZED))
    await session.commit()


async def save_score(session: AsyncSession, entry_id: int, output: L1ScoreOutput, model: str) -> None:
    stmt = pg_insert(Score).values(
        entry_id=entry_id,
        relevance_agents=output.relevance.agents,
        relevance_eval=output.relevance.eval,
        relevance_product=output.relevance.product,
        relevance_engineering=output.relevance.engineering,
        relevance_biz=output.relevance.biz,
        novelty=output.novelty,
        actionability=output.actionability,
        credibility=output.credibility,
        overall=output.overall,
        grade=Grade(output.grade),
        rationale=output.rationale,
        push_recommended=output.push_recommended,
        model=model,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Score.entry_id],
        set_={
            "relevance_agents": output.relevance.agents,
            "relevance_eval": output.relevance.eval,
            "relevance_product": output.relevance.product,
            "relevance_engineering": output.relevance.engineering,
            "relevance_biz": output.relevance.biz,
            "novelty": output.novelty,
            "actionability": output.actionability,
            "credibility": output.credibility,
            "overall": output.overall,
            "grade": Grade(output.grade),
            "rationale": output.rationale,
            "push_recommended": output.push_recommended,
            "model": model,
        },
    )
    await session.execute(stmt)
    await session.execute(update(Entry).where(Entry.id == entry_id).values(status=EntryStatus.SCORED))
    await session.commit()


async def save_verification(
    session: AsyncSession, entry_id: int, output: L2VerifyOutput, model: str
) -> None:
    stmt = pg_insert(Verification).values(
        entry_id=entry_id,
        verdict=output.verdict,
        verified_claims=[claim.model_dump() for claim in output.verified_claims],
        unverified_claims=[claim.model_dump() for claim in output.unverified_claims],
        evidence=[ev.model_dump() for ev in output.evidence],
        notes=output.notes,
        confidence=output.confidence,
        model=model,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Verification.entry_id],
        set_={
            "verdict": output.verdict,
            "verified_claims": [claim.model_dump() for claim in output.verified_claims],
            "unverified_claims": [claim.model_dump() for claim in output.unverified_claims],
            "evidence": [ev.model_dump() for ev in output.evidence],
            "notes": output.notes,
            "confidence": output.confidence,
            "model": model,
        },
    )
    await session.execute(stmt)
    await session.execute(update(Entry).where(Entry.id == entry_id).values(status=EntryStatus.VERIFIED))
    await session.commit()


async def mark_entry_pushed(session: AsyncSession, entry_id: int) -> None:
    await session.execute(update(Entry).where(Entry.id == entry_id).values(status=EntryStatus.PUSHED))
    await session.commit()


async def create_push_event(
    session: AsyncSession,
    *,
    entry_id: int | None,
    push_type: PushType,
    telegram_chat_id: int,
    payload: dict[str, object],
    status: PushStatus,
    telegram_message_id: int | None = None,
    error: str | None = None,
) -> None:
    stmt = insert(PushEvent).values(
        entry_id=entry_id,
        type=push_type,
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=telegram_message_id,
        payload=payload,
        status=status,
        error=error,
    )
    await session.execute(stmt)
    await session.commit()


async def get_entry_for_processing(session: AsyncSession, entry_id: int) -> Entry | None:
    return await session.get(Entry, entry_id)


async def get_summary(session: AsyncSession, entry_id: int) -> Summary | None:
    stmt: Select[tuple[Summary]] = select(Summary).where(Summary.entry_id == entry_id)
    return await session.scalar(stmt)


async def get_score(session: AsyncSession, entry_id: int) -> Score | None:
    stmt: Select[tuple[Score]] = select(Score).where(Score.entry_id == entry_id)
    return await session.scalar(stmt)


async def get_recent_top(session: AsyncSession, hours: int, limit: int = 10) -> list[tuple[Entry, Score]]:
    threshold = _utc_now() - timedelta(hours=hours)
    stmt: Select[tuple[Entry, Score]] = (
        select(Entry, Score)
        .join(Score, Score.entry_id == Entry.id)
        .where(Entry.published_at >= threshold)
        .order_by(Score.overall.desc())
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return list(rows.all())


async def get_entries_by_topic(
    session: AsyncSession, topic: str, limit: int = 10
) -> list[tuple[Entry, Score, Summary]]:
    mapping = {
        "agents": Score.relevance_agents,
        "eval": Score.relevance_eval,
        "product": Score.relevance_product,
        "engineering": Score.relevance_engineering,
        "biz": Score.relevance_biz,
    }
    metric = mapping.get(topic)
    if metric is None:
        return []

    stmt = (
        select(Entry, Score, Summary)
        .join(Score, Score.entry_id == Entry.id)
        .join(Summary, Summary.entry_id == Entry.id)
        .order_by(metric.desc())
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return list(rows.all())


async def save_daily_report(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
    report_markdown: str,
    report_json: dict[str, object],
) -> int:
    stmt = insert(DailyReport).values(
        window_start=window_start,
        window_end=window_end,
        report_markdown=report_markdown,
        report_json=report_json,
    ).returning(DailyReport.id)
    report_id = await session.scalar(stmt)
    await session.commit()
    if report_id is None:
        raise RuntimeError("Failed to save daily report")
    return int(report_id)


async def get_latest_report(session: AsyncSession) -> DailyReport | None:
    stmt: Select[tuple[DailyReport]] = (
        select(DailyReport).order_by(DailyReport.window_end.desc()).limit(1)
    )
    return await session.scalar(stmt)


async def get_report_by_time_keyword(session: AsyncSession, keyword: str) -> DailyReport | None:
    if keyword == "latest":
        return await get_latest_report(session)

    today = _utc_now().date()
    target_day = today if keyword == "today" else today - timedelta(days=1)
    stmt: Select[tuple[DailyReport]] = (
        select(DailyReport)
        .where(func.date(DailyReport.window_end) == target_day)
        .order_by(DailyReport.window_end.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


async def query_for_rag(session: AsyncSession, query: str, limit: int = 5) -> list[tuple[int, str, str, str]]:
    del query
    stmt = (
        select(Entry.id, Entry.title, Entry.url, Summary.tldr)
        .join(Summary, Summary.entry_id == Entry.id)
        .order_by(Entry.published_at.desc())
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return [(int(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows.all()]


async def clear_old_push_events(session: AsyncSession, days: int = 30) -> int:
    threshold = _utc_now() - timedelta(days=days)
    stmt = delete(PushEvent).where(PushEvent.created_at < threshold)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0


async def mark_telegram_update_processed(session: AsyncSession, update_id: int) -> bool:
    stmt = (
        pg_insert(ProcessedTelegramUpdate)
        .values(update_id=update_id)
        .on_conflict_do_nothing(index_elements=[ProcessedTelegramUpdate.update_id])
        .returning(ProcessedTelegramUpdate.id)
    )
    created_id = await session.scalar(stmt)
    await session.commit()
    return created_id is not None
