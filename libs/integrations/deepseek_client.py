from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from libs.core.metrics import LLM_CALLS_TOTAL, LLM_ERRORS_TOTAL, LLM_RETRY_TOTAL, LLM_TOKENS_TOTAL
from libs.core.schemas.llm import (
    ChatOutput,
    L0SummaryOutput,
    L1ScoreOutput,
    L2VerifyOutput,
    LLMUsage,
)
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

    async def summarize(
        self, title: str, url: str, content_text: str
    ) -> tuple[L0SummaryOutput, LLMUsage | None]:
        system = (
            "You are a structured summarizer. Output strict JSON only. "
            "Use Chinese as primary language and keep technical terms in English."
        )
        prompt = (
            "Summarize the article into this schema: language,tldr,key_points,ai_pm_takeaways,tags,"
            "entities,claims,risk_flags,reading_time_min,summary_confidence. "
            f"Title: {title}\nURL: {url}\nContent:\n{content_text[:12000]}"
        )
        return await self._chat_json(
            self._settings.llm_model_summary,
            system,
            prompt,
            L0SummaryOutput,
            task="summary",
        )

    async def score(
        self, title: str, url: str, summary_json: dict[str, Any]
    ) -> tuple[L1ScoreOutput, LLMUsage | None]:
        system = "You are an article scorer. Output strict JSON only."
        prompt = (
            "Score with relevance(agents,eval,product,engineering,biz), novelty, actionability, credibility,"
            " overall, grade(A|B|C), rationale, push_recommended."
            " Use weighted overall:\n"
            "agents 0.22, eval 0.18, product 0.18, engineering 0.16, biz 0.12, novelty 0.08, "
            "actionability 0.04, credibility 0.02. "
            f"Title: {title}\nURL: {url}\nSummary: {json.dumps(summary_json, ensure_ascii=False)}"
        )
        return await self._chat_json(
            self._settings.llm_model_score,
            system,
            prompt,
            L1ScoreOutput,
            task="score",
        )

    async def verify(
        self,
        title: str,
        url: str,
        content_text: str,
        summary_json: dict[str, Any],
        citations: list[dict[str, str]],
        fallback_evidence: list[dict[str, str]],
    ) -> tuple[L2VerifyOutput, LLMUsage | None]:
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
        return await self._chat_json(
            self._settings.llm_model_verify,
            system,
            prompt,
            L2VerifyOutput,
            task="verify",
        )

    async def chat_answer(self, question: str, context_items: list[dict[str, Any]]) -> ChatOutput:
        system = "You are a Telegram research assistant. Output strict JSON only."
        prompt = (
            "Answer user's question using the context. Must provide answer, sources, followups."
            f"\nQuestion: {question}\nContext: {json.dumps(context_items, ensure_ascii=False)}"
        )
        output, _ = await self._chat_json(
            self._settings.llm_model_chat,
            system,
            prompt,
            ChatOutput,
            task="chat",
        )
        return output

    async def _chat_json(
        self,
        model: str,
        system: str,
        prompt: str,
        schema: type[SchemaT],
        *,
        task: str,
    ) -> tuple[SchemaT, LLMUsage | None]:
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
                LLM_CALLS_TOTAL.labels(task=task).inc()
                resp = await self._client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                raw = resp.json()
                content = raw["choices"][0]["message"]["content"]
                data = _extract_json(content)
                data = _coerce_schema_payload(schema, data)
                usage = _parse_usage(raw.get("usage"))
                if usage is not None:
                    LLM_TOKENS_TOTAL.labels(task=task, kind="prompt").inc(usage.prompt_tokens)
                    LLM_TOKENS_TOTAL.labels(task=task, kind="completion").inc(
                        usage.completion_tokens
                    )
                    LLM_TOKENS_TOTAL.labels(task=task, kind="total").inc(usage.total_tokens)
                return schema.model_validate(data), usage
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


def _coerce_schema_payload(schema: type[BaseModel], data: dict[str, Any]) -> dict[str, Any]:
    if schema is L0SummaryOutput:
        return _coerce_l0_summary_payload(data)
    return data


def _coerce_l0_summary_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    payload["key_points"] = _coerce_key_points(payload.get("key_points"))
    payload["ai_pm_takeaways"] = _coerce_takeaways(payload.get("ai_pm_takeaways"))
    payload["entities"] = _coerce_entities(payload.get("entities"))
    payload["claims"] = _coerce_claims(payload.get("claims"))
    payload["risk_flags"] = _coerce_risk_flags(payload.get("risk_flags"))
    payload["tags"] = _coerce_string_list(payload.get("tags"))
    payload["reading_time_min"] = _coerce_non_negative_int(payload.get("reading_time_min"), default=1)
    payload["summary_confidence"] = _coerce_unit_float(
        payload.get("summary_confidence"), default=0.5
    )
    payload["language"] = str(payload.get("language") or "zh")
    payload["tldr"] = str(payload.get("tldr") or "")
    return payload


def _parse_usage(raw: Any) -> LLMUsage | None:
    if not isinstance(raw, dict):
        return None
    prompt_tokens = raw.get("prompt_tokens")
    completion_tokens = raw.get("completion_tokens")
    total_tokens = raw.get("total_tokens")
    if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int) or not isinstance(
        total_tokens, int
    ):
        return None
    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _coerce_key_points(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            result.append(
                {
                    "point": str(item.get("point") or item.get("title") or item.get("claim") or ""),
                    "evidence": str(item.get("evidence") or item.get("why") or item.get("source") or ""),
                    "confidence": _coerce_unit_float(item.get("confidence"), default=0.5),
                }
            )
            continue
        result.append({"point": str(item), "evidence": "", "confidence": 0.5})
    return [row for row in result if row["point"]]


def _coerce_takeaways(value: Any) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else []
    result: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            takeaway = str(item.get("takeaway") or item.get("point") or item.get("summary") or "")
            result.append(
                {
                    "takeaway": takeaway,
                    "why": str(item.get("why") or item.get("reason") or ""),
                    "action": str(item.get("action") or item.get("next_step") or ""),
                }
            )
            continue
        result.append({"takeaway": str(item), "why": "", "action": ""})
    return [row for row in result if row["takeaway"]]


def _coerce_entities(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "companies": [],
        "projects": [],
        "papers": [],
        "people": [],
    }
    if isinstance(value, dict):
        result["companies"] = _coerce_string_list(value.get("companies"))
        result["projects"] = _coerce_string_list(value.get("projects"))
        result["people"] = _coerce_string_list(value.get("people"))
        papers = value.get("papers")
        if isinstance(papers, list):
            result["papers"] = [
                {
                    "title": str(item.get("title") or item.get("name") or ""),
                    "url": str(item.get("url") or ""),
                }
                for item in papers
                if isinstance(item, dict) and (item.get("title") or item.get("name"))
            ]
        return result

    if not isinstance(value, list):
        return result

    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("title") or "")
            kind = str(item.get("type") or "").lower()
            if not name:
                continue
            if "company" in kind or "org" in kind:
                result["companies"].append(name)
            elif "project" in kind or "product" in kind:
                result["projects"].append(name)
            elif "paper" in kind:
                result["papers"].append({"title": name, "url": str(item.get("url") or "")})
            else:
                result["people"].append(name)
        else:
            result["people"].append(str(item))
    return result


def _coerce_claims(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            claim = str(item.get("claim") or item.get("statement") or item.get("point") or "")
            result.append(
                {
                    "claim": claim,
                    "type": str(item.get("type") or "claim"),
                    "needs_verification": bool(item.get("needs_verification", True)),
                }
            )
            continue
        result.append({"claim": str(item), "type": "claim", "needs_verification": True})
    return [row for row in result if row["claim"]]


def _coerce_risk_flags(value: Any) -> list[str]:
    items = value if isinstance(value, list) else []
    result: list[str] = []
    for item in items:
        if isinstance(item, dict):
            flag = item.get("flag") or item.get("label") or item.get("name")
            if flag:
                result.append(str(flag))
            continue
        result.append(str(item))
    return [item for item in result if item]


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _coerce_non_negative_int(value: Any, *, default: int) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _coerce_unit_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(parsed, 1.0))
