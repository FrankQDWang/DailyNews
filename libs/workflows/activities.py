from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from temporalio import activity

from libs.core.db.enums import EntryStatus, Grade, PushStatus, PushType, VerificationVerdict
from libs.core.db.models import Entry, Score, Summary, Verification
from libs.core.db.repositories import (
    create_push_event,
    get_entry_for_processing,
    get_latest_report,
    get_score,
    mark_entry_failed,
    mark_entry_pushed,
    query_for_rag,
    save_daily_report,
    save_score,
    save_summary,
    save_verification,
    upsert_entry,
)
from libs.core.db.session import SessionFactory
from libs.core.metrics import MINIFLUX_FETCH_CONTENT_FAILURES, NEW_ENTRIES_FOUND, TASKS_TOTAL
from libs.core.settings import get_settings
from libs.integrations.deepseek_client import DeepSeekClient
from libs.integrations.miniflux_client import MinifluxClient
from libs.integrations.tavily_client import TavilyClient
from libs.integrations.telegram_client import TelegramClient

logger = logging.getLogger(__name__)
settings = get_settings()


def _grade_is_a(score: str) -> bool:
    return score.upper() == Grade.A.value


@activity.defn
async def refresh_miniflux_activity() -> None:
    TASKS_TOTAL.labels(type="refresh_miniflux").inc()
    client = MinifluxClient(settings)
    try:
        await client.refresh_feeds()
    finally:
        await client.close()


@activity.defn
async def list_unread_miniflux_activity(limit: int = 100) -> list[dict[str, object]]:
    TASKS_TOTAL.labels(type="list_unread_miniflux").inc()
    client = MinifluxClient(settings)
    try:
        entries = await client.list_unread_entries(limit=limit)
    finally:
        await client.close()

    NEW_ENTRIES_FOUND.inc(len(entries))
    return [asdict(entry) for entry in entries]


@activity.defn
async def fetch_and_upsert_entry_activity(entry_payload: dict[str, object]) -> int:
    TASKS_TOTAL.labels(type="fetch_and_upsert_entry").inc()
    entry_id = int(entry_payload["id"])
    client = MinifluxClient(settings)
    try:
        fetched = await client.fetch_content(entry_id)
    except Exception:  # noqa: BLE001
        MINIFLUX_FETCH_CONTENT_FAILURES.inc()
        fetched = None
    finally:
        await client.close()

    src = fetched if fetched is not None else _payload_to_entry(entry_payload)

    async with SessionFactory() as session:
        return await upsert_entry(
            session,
            miniflux_entry_id=src["id"],
            miniflux_feed_id=src["feed_id"],
            url=src["url"],
            title=src["title"],
            author=src["author"],
            published_at=src["published_at"],
            fetched_at=datetime.now(UTC),
            content_html=src["content"],
            content_text=src["content"],
        )


def _payload_to_entry(payload: dict[str, object]) -> dict[str, object]:
    published = payload.get("published_at")
    published_at = None
    if isinstance(published, str):
        published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
    return {
        "id": int(payload["id"]),
        "feed_id": int(payload["feed_id"]) if payload.get("feed_id") else None,
        "url": str(payload.get("url", "")),
        "title": str(payload.get("title", "")),
        "author": str(payload["author"]) if payload.get("author") else None,
        "published_at": published_at,
        "content": str(payload["content"]) if payload.get("content") else "",
    }


@activity.defn
async def summarize_entry_activity(entry_id: int) -> dict[str, object]:
    TASKS_TOTAL.labels(type="summarize_entry").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        if not entry:
            raise RuntimeError(f"Entry not found: {entry_id}")
        if not entry.content_text:
            await mark_entry_failed(session, entry_id, "empty content_text")
            raise RuntimeError(f"Entry {entry_id} has empty content")

        client = DeepSeekClient(settings)
        try:
            output = await client.summarize(entry.title, entry.url, entry.content_text)
            await save_summary(session, entry_id, output, settings.llm_model_summary)
            return output.model_dump()
        except Exception as exc:  # noqa: BLE001
            await mark_entry_failed(session, entry_id, f"summarize failed: {exc}")
            raise
        finally:
            await client.close()


@activity.defn
async def score_entry_activity(entry_id: int) -> dict[str, object]:
    TASKS_TOTAL.labels(type="score_entry").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        summary = await session.scalar(select(Summary).where(Summary.entry_id == entry_id))
        if not entry or not summary:
            raise RuntimeError(f"Missing entry/summary for {entry_id}")

        client = DeepSeekClient(settings)
        try:
            output = await client.score(entry.title, entry.url, summary.summary_json)
            await save_score(session, entry_id, output, settings.llm_model_score)
            return output.model_dump()
        except Exception as exc:  # noqa: BLE001
            await mark_entry_failed(session, entry_id, f"score failed: {exc}")
            raise
        finally:
            await client.close()


@activity.defn
async def verify_entry_activity(entry_id: int) -> dict[str, object]:
    TASKS_TOTAL.labels(type="verify_entry").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        summary = await session.scalar(select(Summary).where(Summary.entry_id == entry_id))
        if not entry or not summary:
            raise RuntimeError(f"Missing entry/summary for verify {entry_id}")

        citations = _extract_links(summary.summary_json)
        tavily = TavilyClient(settings)
        fallback_evidence = await tavily.search(f"{entry.title} {entry.url}", max_results=3)
        await tavily.close()

        client = DeepSeekClient(settings)
        try:
            output = await client.verify(
                title=entry.title,
                url=entry.url,
                content_text=entry.content_text or "",
                summary_json=summary.summary_json,
                citations=citations,
                fallback_evidence=fallback_evidence,
            )
            await save_verification(session, entry_id, output, settings.llm_model_verify)
            return output.model_dump()
        except Exception as exc:  # noqa: BLE001
            await mark_entry_failed(session, entry_id, f"verify failed: {exc}")
            raise
        finally:
            await client.close()


@activity.defn
async def should_push_activity(entry_id: int) -> bool:
    TASKS_TOTAL.labels(type="should_push").inc()
    async with SessionFactory() as session:
        score = await get_score(session, entry_id)
        if score is None:
            return False
        if score.grade != Grade.A:
            return False

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(Entry.id).where(
            Entry.updated_at >= today_start,
            Entry.status == EntryStatus.PUSHED,
        )
        pushed_today = len((await session.execute(stmt)).all())
        return pushed_today < settings.a_push_limit_per_day


@activity.defn
async def send_alert_activity(entry_id: int) -> None:
    TASKS_TOTAL.labels(type="send_alert").inc()
    async with SessionFactory() as session:
        entry = await get_entry_for_processing(session, entry_id)
        summary = await session.scalar(select(Summary).where(Summary.entry_id == entry_id))
        score = await get_score(session, entry_id)
        verification = await session.scalar(
            select(Verification).where(Verification.entry_id == entry_id)
        )
        if not entry or not summary or not score:
            raise RuntimeError(f"Missing data for alert {entry_id}")

        verification_line = "未核验"
        if verification is not None:
            verification_line = "核验已完成"

        body = (
            f"【{score.grade.value}】{entry.title}\n"
            f"- {summary.tldr}\n"
            f"评分：{score.grade.value} | Overall: {score.overall:.2f}\n"
            f"核验：{verification_line}\n"
            f"链接：{entry.url}\n"
            f"ID：E{entry.id}"
        )

        tg = TelegramClient(settings.telegram_bot_token)
        try:
            message_ids = await tg.send_markdown(settings.telegram_target_chat_id, body)
        finally:
            await tg.close()

        await create_push_event(
            session,
            entry_id=entry_id,
            push_type=PushType.ALERT,
            telegram_chat_id=settings.telegram_target_chat_id,
            payload={"message": body},
            status=PushStatus.SENT,
            telegram_message_id=message_ids[-1] if message_ids else None,
        )
        await mark_entry_pushed(session, entry_id)


def _extract_links(summary_json: dict[str, object]) -> list[dict[str, str]]:
    entities = summary_json.get("entities", {})
    if not isinstance(entities, dict):
        return []
    papers = entities.get("papers", [])
    if not isinstance(papers, list):
        return []

    links: list[dict[str, str]] = []
    for item in papers:
        if isinstance(item, dict):
            title = str(item.get("title", ""))
            url = str(item.get("url", ""))
            if url:
                links.append({"title": title, "url": url})
    return links


@activity.defn
async def build_digest_activity() -> dict[str, object]:
    TASKS_TOTAL.labels(type="build_digest").inc()
    async with SessionFactory() as session:
        latest = await get_latest_report(session)
        window_start = latest.window_end if latest else datetime.now(UTC) - timedelta(days=1)
        window_end = datetime.now(UTC)

        stmt = (
            select(Entry, Score)
            .join(Score, Score.entry_id == Entry.id)
            .where(Entry.published_at >= window_start, Entry.published_at < window_end)
            .order_by(Score.overall.desc())
            .limit(30)
        )
        rows = (await session.execute(stmt)).all()

        top_items = [
            {
                "entry_id": int(entry.id),
                "title": entry.title,
                "url": entry.url,
                "why_important": score.rationale,
            }
            for entry, score in rows[:5]
        ]
        report_json = {
            "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
            "top_items": top_items,
            "clusters": [],
            "trend_radar": [],
            "action_recommendations": [],
        }
        markdown = _render_digest_markdown(report_json)

        report_id = await save_daily_report(session, window_start, window_end, markdown, report_json)
        return {"report_id": report_id, "markdown": markdown}


def _render_digest_markdown(report_json: dict[str, object]) -> str:
    window = report_json.get("window", {})
    top_items = report_json.get("top_items", [])
    lines = [
        f"📌 日报（窗口：{window.get('start')} ~ {window.get('end')}）",
        "",
        "Top 5:",
    ]
    for idx, item in enumerate(top_items, start=1):
        if isinstance(item, dict):
            lines.append(
                f"{idx}. {item.get('title')}（ID: E{item.get('entry_id')}）\\n{item.get('why_important')}\\n{item.get('url')}"
            )
    return "\n".join(lines)


@activity.defn
async def send_digest_activity(markdown: str) -> None:
    TASKS_TOTAL.labels(type="send_digest").inc()
    tg = TelegramClient(settings.telegram_bot_token)
    try:
        await tg.send_markdown(settings.telegram_target_chat_id, markdown)
    finally:
        await tg.close()


@activity.defn
async def generate_chat_answer_activity(question: str) -> dict[str, object]:
    TASKS_TOTAL.labels(type="generate_chat_answer").inc()
    async with SessionFactory() as session:
        rows = await query_for_rag(session, question, limit=5)
        context = [
            {"entry_id": item[0], "title": item[1], "url": item[2], "summary": item[3]}
            for item in rows
        ]

    client = DeepSeekClient(settings)
    try:
        output = await client.chat_answer(question, context)
    finally:
        await client.close()

    return output.model_dump()


@activity.defn
async def deepdive_activity(entry_id: int, requestor_chat_id: int) -> None:
    TASKS_TOTAL.labels(type="deepdive").inc()
    verification = await verify_entry_activity(entry_id)
    verdict = verification.get("verdict", VerificationVerdict.UNCERTAIN.value)

    text = (
        f"DeepDive 结果（E{entry_id}）\n"
        f"核验结论：{verdict}\n"
        f"说明：{verification.get('notes', '')}"
    )

    tg = TelegramClient(settings.telegram_bot_token)
    try:
        await tg.send_markdown(requestor_chat_id, text)
    finally:
        await tg.close()
