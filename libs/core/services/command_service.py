from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.core.db.models import Entry, Score, Summary, Verification
from libs.core.db.repositories import (
    get_entries_by_topic,
    get_recent_top,
    get_report_by_time_keyword,
    query_for_rag,
)
from libs.core.schemas.llm import ChatOutput
from libs.integrations.deepseek_client import DeepSeekClient


class CommandService:
    def __init__(self, deepseek: DeepSeekClient) -> None:
        self._deepseek = deepseek

    async def help_text(self) -> str:
        return (
            "可用命令：\n"
            "/ask <问题>\n"
            "/top <6h|24h|7d>\n"
            "/digest [latest|today|yesterday]\n"
            "/topic <agents|eval|product|engineering|biz>\n"
            "/read <id>\n"
            "/deepdive <id>\n"
            "/config (admin)\n"
            "/set <key> <value> (admin)\n"
            "/reindex (admin)"
        )

    async def ask(self, session: AsyncSession, question: str) -> str:
        rows = await query_for_rag(session, question, limit=5)
        context = [
            {"entry_id": row[0], "title": row[1], "url": row[2], "summary": row[3]} for row in rows
        ]
        output: ChatOutput = await self._deepseek.chat_answer(question, context)
        src_lines = [
            f"{idx}. {source.get('title')}（ID: E{source.get('entry_id')}）{source.get('url')}"
            for idx, source in enumerate(output.sources[:5], start=1)
        ]
        followup_lines = [f"- {item}" for item in output.followups[:3]]
        return (
            f"【回答】\n{output.answer}\n\n"
            f"【依据（最近资料）】\n" + "\n".join(src_lines) + "\n\n"
            "【你可以继续问】\n" + "\n".join(followup_lines)
        )

    async def top(self, session: AsyncSession, arg: str | None) -> str:
        hours_map = {"6h": 6, "24h": 24, "7d": 24 * 7}
        hours = hours_map.get((arg or "24h").lower(), 24)
        rows = await get_recent_top(session, hours=hours, limit=10)
        if not rows:
            return "最近窗口内没有可展示的条目。"

        lines = [f"最近 {arg or '24h'} Top 10："]
        for idx, (entry, score) in enumerate(rows, start=1):
            lines.append(
                f"{idx}. [{score.grade.value}] {entry.title} — {score.rationale}（ID: E{entry.id}）{entry.url}"
            )
        return "\n".join(lines)

    async def digest(self, session: AsyncSession, arg: str | None) -> str:
        keyword = (arg or "latest").lower()
        report = await get_report_by_time_keyword(session, keyword)
        if report is None:
            return "暂无日报数据。"
        return report.report_markdown

    async def topic(self, session: AsyncSession, arg: str | None) -> str:
        if not arg:
            return "用法：/topic agents|eval|product|engineering|biz"
        topic = arg.strip().lower()
        rows = await get_entries_by_topic(session, topic=topic, limit=10)
        if not rows:
            return f"主题 {topic} 暂无结果。"

        lines = [f"主题 {topic} 最近 10 条："]
        for idx, (entry, score, summary) in enumerate(rows, start=1):
            lines.append(
                f"{idx}. [{score.grade.value}] {entry.title}（ID: E{entry.id}）\n{summary.tldr}\n{entry.url}"
            )
        return "\n".join(lines)

    async def read(self, session: AsyncSession, arg: str | None) -> str:
        if not arg or not arg.isdigit():
            return "用法：/read <id>"
        entry_id = int(arg)

        entry = await session.get(Entry, entry_id)
        score = await session.scalar(select(Score).where(Score.entry_id == entry_id))
        summary = await session.scalar(select(Summary).where(Summary.entry_id == entry_id))
        verification = await session.scalar(
            select(Verification).where(Verification.entry_id == entry_id)
        )
        if not entry or not score or not summary:
            return f"未找到 ID=E{entry_id} 的完整记录。"

        lines = [
            f"{entry.title}",
            f"评分：{score.grade.value} | overall={score.overall:.2f}",
            f"摘要：{summary.tldr}",
            f"链接：{entry.url}",
        ]
        if verification:
            lines.append(f"核验：{verification.verdict.value}（{verification.confidence:.2f}）")
        lines.append(f"如需深挖：/deepdive {entry_id}")
        return "\n".join(lines)

    async def config_text(self, chat_id: int) -> str:
        now = datetime.now(UTC).isoformat()
        return f"当前配置快照（chat={chat_id}）\n更新时间：{now}"
