# ADR 0005: Reduce Fetch Churn and Add LLM Usage Telemetry

- Status: Accepted
- Date: 2026-03-17

## Context
Railway metrics showed `assistant-api` was cheap, while `assistant-worker` and Miniflux were doing most of the real work. Logs confirmed the main waste pattern: many unread rows still triggered `fetch-content?update_content=true`, including rows that were already terminal locally or repeatedly failed upstream with `429/500`. At the same time, the system had no first-class token telemetry for `summary`, `score`, and `verify`, so resource discussions still depended on rough inference.

## Decision
Implement phases 0-4 of the resource optimization plan.

1. Add explicit fetch-state tracking on `entries`: `ready`, `cooldown`, and `blocked`, plus failure counters, next retry time, and last fetch error.
2. Make ingest metadata-first: unread rows are upserted and classified before any `fetch-content` call. Terminal, cooldown, and blocked rows skip full-content fetch entirely.
3. Move retryable fetch failures through a fixed backoff ladder to `blocked`. Blocked rows are read-synced out of Miniflux so they stop occupying the unread window.
4. Change ingest cadence from “fetch 100 and fan out everything” to “scan 300, process at most 30 actionable rows.”
5. Add LLM usage telemetry (`prompt_tokens`, `completion_tokens`, `total_tokens`) to `summaries`, `scores`, and `verifications`, and expose 24-hour totals in the internal debug snapshot.
6. Quarantine `too_short_content` before LLM, using the same terminal path as `empty_content`.

## Alternatives Considered
- Keep eager `fetch-content` and only shrink the cron batch size. Rejected because it would still waste Miniflux and worker capacity on already terminal rows.
- Add a generic remote-cache layer for fetched content. Rejected because the bigger win is to avoid unnecessary fetches altogether, not cache more of them.
- Optimize `assistant-api` memory/CPU first. Rejected because observed metrics show the API is not the bottleneck.
- Merge `summary + score` immediately. Rejected for this round because it changes model behavior and deserves a separate validation phase.

## Consequences
- Positive: Repeated Miniflux full-content fetches should drop sharply, especially for terminal or failing rows.
- Positive: Worker fan-out and per-run token bursts are capped by design.
- Positive: Operators can now see LLM token usage in `/internal/debug/overview` instead of inferring it from row counts.
- Positive: `too_short_content` no longer burns LLM calls.
- Negative: `content_text` may stay at metadata-level content until a row is selected as actionable and fetched in full.
- Negative: `blocked` rows are automatically marked read, so recovery now depends on explicit `internal_reprocess`.

## Outcome
Implemented with a new migration for fetch-state and usage columns, metadata-first ingest activities, capped actionable fan-out, extended debug metrics, and regression tests for cooldown/block/quarantine behavior.
