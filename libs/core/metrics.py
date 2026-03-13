from __future__ import annotations

from prometheus_client import Counter, Histogram

INGEST_RUNS_TOTAL = Counter("ingest_runs_total", "Total ingest runs")
INGEST_RUNS_FAILED = Counter("ingest_runs_failed", "Failed ingest runs")
NEW_ENTRIES_FOUND = Counter("new_entries_found", "New entries discovered")
MINIFLUX_FETCH_CONTENT_FAILURES = Counter(
    "miniflux_fetch_content_failures", "Failed miniflux fetch-content calls"
)

TASKS_TOTAL = Counter("tasks_total", "Total workflow activities", ["type"])
TASK_LATENCY_MS = Histogram("task_latency_ms", "Task execution latency", ["type"])
LLM_ERRORS_TOTAL = Counter("llm_errors_total", "LLM errors")
LLM_RETRY_TOTAL = Counter("llm_retry_total", "LLM retries")

MESSAGES_SENT_TOTAL = Counter("messages_sent_total", "Telegram messages sent")
TELEGRAM_429_TOTAL = Counter("telegram_429_total", "Telegram rate-limit responses")
SEND_LATENCY_MS = Histogram("send_latency_ms", "Telegram send latency ms")
