# ADR 0007: Stop Counting Expected Process Exits as Workflow Failures

- Status: Accepted
- Date: 2026-03-17

## Context

`ProcessEntryWorkflow` was still ending in Temporal `FAILED` for two expected business outcomes:

- retryable `fetch-content` failures that already moved entries into `cooldown` or `blocked`
- low-value content that was already being quarantined as `empty_content` or `too_short_content`

That made production failure rate, worker alerts, and resource analysis noisy. It also made it hard to distinguish real system errors from valid early exits.

## Decision

Add explicit process-outcome audit fields on `entries` and insert a preflight activity before `summarize/score`.

- `prepare_entry_content_activity(entry_id)` now decides whether the entry is:
  - `ready`
  - `quarantined`
  - `fetch_deferred`
- `ProcessEntryWorkflow` exits successfully when preflight returns `quarantined` or `fetch_deferred`.
- `entries` now stores:
  - `last_process_outcome`
  - `last_process_reason`
  - `last_processed_at`

Only unexpected exceptions in code, DB, LLM, verification, or push paths should remain Temporal workflow failures.

## Alternatives Considered

- Keep using Temporal `FAILED` and infer expected exits from log messages only.
- Add a new enum-backed process outcome type instead of plain `TEXT`.
- Move more state into Temporal workflow return values instead of persisting it on `entries`.

## Consequences

- Operational dashboards can now separate expected process exits from real failures.
- Internal debug output becomes sufficient to explain why a row stopped processing.
- This adds one migration and expands the internal debug payload, but avoids new replay-sensitive enum types.

## Outcome

- Implemented in code, validated locally, pending production verification after deploy.
