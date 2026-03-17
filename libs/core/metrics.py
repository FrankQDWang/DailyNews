from __future__ import annotations

from prometheus_client import Counter, Histogram

INGEST_RUNS_TOTAL = Counter("ingest_runs_total", "Total ingest runs")
INGEST_RUNS_FAILED = Counter("ingest_runs_failed", "Failed ingest runs")
NEW_ENTRIES_FOUND = Counter("new_entries_found", "New entries discovered")
MINIFLUX_FETCH_CONTENT_FAILURES = Counter(
    "miniflux_fetch_content_failures", "Failed miniflux fetch-content calls"
)
MINIFLUX_FETCH_CONTENT_ATTEMPT_TOTAL = Counter(
    "miniflux_fetch_content_attempt_total", "Attempted miniflux fetch-content calls"
)
MINIFLUX_FETCH_CONTENT_SKIPPED_TOTAL = Counter(
    "miniflux_fetch_content_skipped_total",
    "Skipped miniflux fetch-content calls",
    ["reason"],
)
MINIFLUX_FETCH_CONTENT_BLOCKED_TOTAL = Counter(
    "miniflux_fetch_content_blocked_total",
    "Entries blocked from miniflux fetch-content after repeated failures",
)

TASKS_TOTAL = Counter("tasks_total", "Total workflow activities", ["type"])
TASK_LATENCY_MS = Histogram("task_latency_ms", "Task execution latency", ["type"])
LLM_ERRORS_TOTAL = Counter("llm_errors_total", "LLM errors")
LLM_RETRY_TOTAL = Counter("llm_retry_total", "LLM retries")
LLM_CALLS_TOTAL = Counter("llm_calls_total", "LLM calls", ["task"])
LLM_TOKENS_TOTAL = Counter("llm_tokens_total", "LLM tokens", ["task", "kind"])

MESSAGES_SENT_TOTAL = Counter("messages_sent_total", "Telegram messages sent")
TELEGRAM_429_TOTAL = Counter("telegram_429_total", "Telegram rate-limit responses")
SEND_LATENCY_MS = Histogram("send_latency_ms", "Telegram send latency ms")
