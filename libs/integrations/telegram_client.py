from __future__ import annotations

import time
from collections import defaultdict

import httpx

from libs.core.metrics import MESSAGES_SENT_TOTAL, SEND_LATENCY_MS, TELEGRAM_429_TOTAL


class TelegramClient:
    def __init__(self, bot_token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{bot_token}",
            timeout=30,
        )
        self._last_send_ts_by_chat: dict[int, float] = defaultdict(float)

    async def close(self) -> None:
        await self._client.aclose()

    async def send_markdown(self, chat_id: int, text: str) -> list[int]:
        message_ids: list[int] = []
        for chunk in split_message(text):
            await self._enforce_per_chat_interval(chat_id)
            start = time.perf_counter()
            resp = await self._client.post(
                "/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            SEND_LATENCY_MS.observe((time.perf_counter() - start) * 1000)
            if resp.status_code == 429:
                TELEGRAM_429_TOTAL.inc()
                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 1))
                await _sleep_seconds(retry_after)
                resp = await self._client.post(
                    "/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                )
            resp.raise_for_status()
            data = resp.json().get("result", {})
            message_ids.append(int(data.get("message_id", 0)))
            MESSAGES_SENT_TOTAL.inc()
            self._last_send_ts_by_chat[chat_id] = time.time()
        return message_ids

    async def _enforce_per_chat_interval(self, chat_id: int) -> None:
        now = time.time()
        elapsed = now - self._last_send_ts_by_chat[chat_id]
        if elapsed < 1.0:
            await _sleep_seconds(1.0 - elapsed)


async def _sleep_seconds(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


def split_message(text: str, chunk_size: int = 3800) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + chunk_size, len(text))
        if end < len(text):
            split = text.rfind("\n", cursor, end)
            if split > cursor:
                end = split
        chunks.append(text[cursor:end].strip())
        cursor = end
    return [chunk for chunk in chunks if chunk]
