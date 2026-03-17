# ADR 0004: Add Verification Audit State

- Status: Accepted
- Date: 2026-03-17

## Context
The pipeline now ingests, summarizes, scores, and quarantines empty-content entries correctly, but the system still cannot explain why `verifications` is empty. A scored row may be legitimately outside the push window, blocked by the daily cap, already pushed under older logic, or genuinely failing verification. Relying on the presence or absence of rows in `verifications` is too indirect for operational debugging.

## Decision
Add explicit verification audit fields directly on `entries`: `verification_state`, `verification_reason`, and `verified_at`. The state space is fixed to `not_required`, `pending`, `verified`, `failed`, and `legacy_gap`.

Push gating now returns a structured decision instead of a bare boolean. The decision writes verification audit state immediately after scoring and before verification runs:

- `non_a` -> `not_required`
- `outside_push_window` -> `not_required`
- `daily_cap_reached` -> `not_required`
- `eligible_for_verification` -> `pending`

Successful verification promotes the row to `verified`. Verification failure records `verification_state=failed` and preserves the row as scored instead of demoting the whole entry lifecycle to global `failed`. Historical scored rows are backfilled once so older pushes without verification become visible as `legacy_gap`.

## Alternatives Considered
- Keep deriving state only from `scores`, `verifications`, and `push_events`. Rejected because it leaves too much ambiguity in production debugging.
- Add a separate verification audit table. Rejected because the per-entry state is single-valued and belongs naturally on `entries`.
- Continue marking verification failure as `entries.status=failed`. Rejected because it conflates “article processing failed” with “verification failed after scoring”.

## Consequences
- Positive: The system can now distinguish “no verification needed” from “verification failed” and from “historical gap”.
- Positive: `/internal/debug/overview` can directly show pending verification candidates and audit counters.
- Positive: Historical rows become explainable without replaying logs.
- Negative: The backfill uses today’s fixed 24-hour window and cannot reconstruct the exact daily-cap context of older rows.

## Outcome
Implemented with new `entries` audit fields, a backfill migration, structured push-decision results, verification-state-aware repository writes, and expanded debug snapshot coverage.
