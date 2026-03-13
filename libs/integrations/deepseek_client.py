from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from libs.core.metrics import LLM_ERRORS_TOTAL, LLM_RETRY_TOTAL
from libs.core.schemas.llm import ChatOutput, L0SummaryOutput, L1ScoreOutput, L2VerifyOutput
from libs.core.settings import Settings

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.deepseek_base_url,
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def summarize(self, title: str, url: str, content_text: str) -> L0SummaryOutput:
        system = (
            "You are a structured summarizer. Output strict JSON only. "
            "Use Chinese as primary language and keep technical terms in English."
        )
        prompt = (
            "Summarize the article into this schema: language,tldr,key_points,ai_pm_takeaways,tags,"
            "entities,claims,risk_flags,reading_time_min,summary_confidence. "
            f"Title: {title}\nURL: {url}\nContent:\n{content_text[:12000]}"
        )
        return await self._chat_json(self._settings.llm_model_summary, system, prompt, L0SummaryOutput)

    async def score(self, title: str, url: str, summary_json: dict[str, Any]) -> L1ScoreOutput:
        system = "You are an article scorer. Output strict JSON only."
        prompt = (
            "Score with relevance(agents,eval,product,engineering,biz), novelty, actionability, credibility,"
            " overall, grade(A|B|C), rationale, push_recommended."
            " Use weighted overall:\n"
            "agents 0.22, eval 0.18, product 0.18, engineering 0.16, biz 0.12, novelty 0.08, "
            "actionability 0.04, credibility 0.02. "
            f"Title: {title}\nURL: {url}\nSummary: {json.dumps(summary_json, ensure_ascii=False)}"
        )
        return await self._chat_json(self._settings.llm_model_score, system, prompt, L1ScoreOutput)

    async def verify(
        self,
        title: str,
        url: str,
        content_text: str,
        summary_json: dict[str, Any],
        citations: list[dict[str, str]],
        fallback_evidence: list[dict[str, str]],
    ) -> L2VerifyOutput:
        system = (
            "You are a strict verifier. Prefer first-hand evidence. Output strict JSON only. "
            "Keep snippets short and avoid long quotes."
        )
        prompt = (
            "Verify claims from the article. Output verdict/confidence/verified_claims/unverified_claims/"
            "evidence/notes/recommended_actions."
            f"\nTitle: {title}\nURL: {url}\nCitations: {json.dumps(citations, ensure_ascii=False)}"
            f"\nFallbackEvidence: {json.dumps(fallback_evidence, ensure_ascii=False)}"
            f"\nSummary: {json.dumps(summary_json, ensure_ascii=False)}"
            f"\nContent: {content_text[:12000]}"
        )
        return await self._chat_json(self._settings.llm_model_verify, system, prompt, L2VerifyOutput)

    async def chat_answer(self, question: str, context_items: list[dict[str, Any]]) -> ChatOutput:
        system = "You are a Telegram research assistant. Output strict JSON only."
        prompt = (
            "Answer user's question using the context. Must provide answer, sources, followups."
            f"\nQuestion: {question}\nContext: {json.dumps(context_items, ensure_ascii=False)}"
        )
        return await self._chat_json(self._settings.llm_model_chat, system, prompt, ChatOutput)

    async def _chat_json(
        self,
        model: str,
        system: str,
        prompt: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                resp = await self._client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                data = _extract_json(content)
                return schema.model_validate(data)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                LLM_ERRORS_TOTAL.inc()
                if attempt < 3:
                    LLM_RETRY_TOTAL.inc()
                    logger.warning("deepseek parse failed attempt=%s error=%s", attempt, exc)
                else:
                    logger.exception("deepseek parse failed after retries")

        raise RuntimeError(f"DeepSeek JSON parse failed: {last_error}")


def _extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        stripped = text.strip("`")
        parts = stripped.split("\n", maxsplit=1)
        text = parts[1] if len(parts) > 1 else stripped
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise
        raw = json.loads(text[start : end + 1])
    if not isinstance(raw, dict):
        raise ValueError("Model output is not a JSON object")
    return raw
