from __future__ import annotations

from typing import Any

import httpx

from libs.core.settings import Settings


class TavilyClient:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.tavily_api_key
        self._base_url = settings.tavily_base_url
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=30)

    async def close(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        if not self._api_key:
            return []
        payload: dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }
        resp = await self._client.post("/search", json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [
            {
                "url": str(item.get("url", "")),
                "title": str(item.get("title", "")),
                "snippet": str(item.get("content", ""))[:240],
            }
            for item in results
        ]
