from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client as TemporalClient

from apps.api.dependencies import require_internal_admin
from libs.core.db.repositories import (
    get_debug_overview,
    mark_telegram_update_processed,
    reset_content_fetch_state,
)
from libs.core.db.session import get_session
from libs.core.logging import configure_logging
from libs.core.metrics import TASKS_TOTAL
from libs.core.rate_limit import SlidingWindowRateLimiter
from libs.core.schemas.commands import parse_command
from libs.core.schemas.debug import DebugOverviewResponse
from libs.core.schemas.telegram import TelegramUpdate
from libs.core.services.command_service import CommandService
from libs.core.settings import Settings, get_settings
from libs.integrations.deepseek_client import DeepSeekClient
from libs.integrations.telegram_client import TelegramClient
from libs.workflows.workflows import DeepDiveWorkflow, ProcessEntryWorkflow

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    app = FastAPI(title="DailyNews API", version="0.1.0")

    rate_limiter = SlidingWindowRateLimiter()
    deepseek = DeepSeekClient(settings)
    telegram = TelegramClient(settings.telegram_bot_token)
    cmd_service = CommandService(deepseek)

    app.state.settings = settings
    app.state.rate_limiter = rate_limiter
    app.state.deepseek = deepseek
    app.state.telegram = telegram
    app.state.cmd_service = cmd_service

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await deepseek.close()
        await telegram.close()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(
        db: AsyncSession = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, str]:
        await db.execute(text("SELECT 1"))
        await TemporalClient.connect(
            settings.temporal_host,
            namespace=settings.temporal_namespace,
        )
        return {"status": "ready"}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/internal/reprocess/{entry_id}")
    async def internal_reprocess(
        entry_id: int,
        _: int = Depends(require_internal_admin),
        db: AsyncSession = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, str]:
        await reset_content_fetch_state(db, entry_id)
        client = await TemporalClient.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        workflow_id = f"manual-reprocess-{entry_id}"
        await client.start_workflow(
            ProcessEntryWorkflow.run,
            entry_id,
            id=workflow_id,
            task_queue=settings.temporal_task_queue_process,
        )
        return {"status": "started", "workflow_id": workflow_id}

    @app.get("/internal/debug/overview", response_model=DebugOverviewResponse)
    async def internal_debug_overview(
        _: int = Depends(require_internal_admin),
        db: AsyncSession = Depends(get_session),
    ) -> DebugOverviewResponse:
        return await get_debug_overview(db)

    @app.post("/telegram/webhook/{secret}")
    async def telegram_webhook(
        secret: str,
        update: TelegramUpdate,
        db: AsyncSession = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, bool]:
        if secret != settings.telegram_webhook_secret:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

        is_new = await mark_telegram_update_processed(db, update.update_id)
        if not is_new:
            return {"ok": True}

        msg = update.message
        if msg is None or not msg.text:
            return {"ok": True}

        parsed = parse_command(msg.text)
        if parsed is None:
            return {"ok": True}

        user_id = (msg.from_.id if msg.from_ is not None else 0)
        chat_id = msg.chat.id

        if parsed.name == "ask":
            allow_user = await rate_limiter.allow(
                key=f"ask-user:{chat_id}:{user_id}",
                limit=settings.rate_limit_user_qpm,
                window_sec=60,
            )
            allow_chat = await rate_limiter.allow(
                key=f"ask-chat:{chat_id}",
                limit=settings.rate_limit_chat_qpm,
                window_sec=60,
            )
            if not allow_user or not allow_chat:
                await telegram.send_markdown(chat_id, "请求过于频繁，请稍后再试。")
                return {"ok": True}
        elif parsed.name == "deepdive":
            allow_deepdive = await rate_limiter.allow(
                key=f"deepdive-user:{chat_id}:{user_id}",
                limit=settings.rate_limit_deepdive_per_day,
                window_sec=24 * 3600,
            )
            if not allow_deepdive:
                await telegram.send_markdown(chat_id, "今天的 /deepdive 配额已用完，请明天再试。")
                return {"ok": True}

        text_reply = await _dispatch_command(
            parsed.name,
            parsed.arg,
            cmd_service,
            db,
            settings,
            chat_id,
            user_id,
        )
        TASKS_TOTAL.labels(type=f"cmd_{parsed.name}").inc()
        await telegram.send_markdown(chat_id, text_reply)
        return {"ok": True}

    return app


async def _dispatch_command(
    name: str,
    arg: str | None,
    cmd_service: CommandService,
    db: AsyncSession,
    settings: Settings,
    chat_id: int,
    user_id: int,
) -> str:
    if name == "help":
        return await cmd_service.help_text()
    if name == "ask":
        if not arg:
            return "用法：/ask <问题>"
        return await cmd_service.ask(db, arg)
    if name == "top":
        return await cmd_service.top(db, arg)
    if name == "digest":
        return await cmd_service.digest(db, arg)
    if name == "topic":
        return await cmd_service.topic(db, arg)
    if name == "read":
        return await cmd_service.read(db, arg)
    if name == "deepdive":
        if not arg or not arg.isdigit():
            return "用法：/deepdive <id>"
        client = await TemporalClient.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        entry_id = int(arg)
        workflow_id = f"deepdive-{entry_id}-{chat_id}-{user_id}"
        await client.start_workflow(
            DeepDiveWorkflow.run,
            args=[entry_id, chat_id, user_id],
            id=workflow_id,
            task_queue=settings.temporal_task_queue_deepdive,
        )
        return f"已开始深挖 E{entry_id}，完成后会 @你返回结果。"

    if name in {"config", "set", "reindex"}:
        if user_id not in settings.telegram_admin_user_ids:
            return "该命令仅管理员可用。"
        if name == "config":
            return await cmd_service.config_text(chat_id)
        if name == "set":
            return "MVP 暂不支持在线修改配置，请通过 Railway Variables / .env 管理。"
        return "已触发重建任务（MVP 占位实现）。"

    return "未知命令，输入 /help 查看可用命令。"


app = create_app()
