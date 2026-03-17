# Exec Plans

Use this file to track complex implementation plans before coding.

## 2026-03-16 Railway Debug

### Context
- Problem: Railway production deploy is partially healthy. `assistant-worker` and cron jobs are up, but `assistant-api` crashes during startup migrations. `cron-ingest` also fails at runtime with `401 Unauthorized` from Miniflux.
- Scope: Fix deployment blockers, keep runtime architecture unchanged, then complete webhook and smoke verification.
- Constraints: Deploy target stays Railway-first. Runtime commands keep using `python ...` instead of `uv run ...`. Secrets must stay out of Git.

### Decisions
- Decision 1: Harden migrations against partially initialized Postgres state instead of relying on one-off manual DB cleanup.
- Decision 2: Re-sync `MINIFLUX_API_TOKEN` on Railway services from the known-good local `.env` value.

### Steps
1. Make `0001_initial` safe to rerun when enum types already exist.
2. Push the fix and wait for GitHub CI to pass.
3. Redeploy Railway services and verify `assistant-api` health.
4. Update Telegram webhook to `assistant-api`.
5. Trigger ingest and complete post-Step-10 smoke checks.

### Acceptance
- [ ] `assistant-api` deployment is `SUCCESS`.
- [ ] `/healthz` and `/readyz` return `200`.
- [ ] `cron-ingest` no longer fails with Miniflux `401`.
- [ ] Telegram webhook points at `assistant-api`.

### Risks & Rollback
- Risk: The database may already contain a partially applied schema beyond enum creation.
- Rollback: Revert to the previous commit and repair the database manually if migrations still fail after hardening.

## 2026-03-16 Debug Snapshot Overview

### Context
- Problem: Production smoke checks no longer block on deployment, but runtime verification still depends too heavily on Railway logs.
- Scope: Add a read-only internal debug endpoint that shows database counts and recent records for ingest, summary, score, verification, push, digest, and Telegram update dedupe.
- Constraints: Reuse existing `x_internal_token + x_admin_user_id` auth, keep the surface HTTP-only, and return JSON-safe fixed-shape data only.

### Decisions
- Decision 1: Extract shared internal-admin auth into a FastAPI dependency so `internal_reprocess` and the new debug endpoint do not duplicate checks.
- Decision 2: Keep v1 narrow: no filters, no HTML, no Temporal state, no raw payload dumps.

### Steps
1. Add shared internal-admin auth dependency.
2. Add `debug` response schemas and a repository-level snapshot query helper.
3. Add `GET /internal/debug/overview`.
4. Add route/repository tests and run lint, typecheck, and pytest.

### Acceptance
- [x] `GET /internal/debug/overview` returns `403` for invalid internal access and `200` for valid admin headers.
- [x] Response includes fixed counts and recent rows for the required tables.
- [x] Response is JSON-safe and does not expose ORM objects or secrets.
- [x] Automated tests cover empty and populated snapshot cases.

### Risks & Rollback
- Risk: The snapshot query could accidentally expose oversized or sensitive fields if it returns ORM objects directly.
- Rollback: Revert the endpoint and keep the shared auth dependency only if tests uncover unsafe response content.

## 2026-03-17 Incremental Push Window and Read Sync

### Context
- Problem: Production ingest is working, but historical Miniflux `unread` backlog can still trigger Telegram pushes and repeated LLM work.
- Scope: Restrict realtime push eligibility to the last 24 hours, mark Miniflux entries as `read` after successful scoring, and skip rerunning summary/score for entries already in terminal local states.
- Constraints: Keep public HTTP and Telegram interfaces unchanged, avoid schema migrations, and preserve historical ingest + summary + score for future RAG.

### Decisions
- Decision 1: Realtime push stays `grade == A`, but now also requires the entry to be within `PUSH_WINDOW_HOURS` and under the daily cap.
- Decision 2: `mark read` failures must not roll back summary/score results; future cron runs should retry read sync without rerunning LLM work.

### Steps
1. Add `PUSH_WINDOW_HOURS` config and Miniflux `mark read` integration support.
2. Change ingest upsert activity to return a JSON-safe entry state contract instead of a bare `entry_id`.
3. Update ingest/process workflows to skip terminal entries, run read-sync after scoring, and gate verify behind push eligibility.
4. Add unit tests for the push window, ingest-state contract, and Miniflux read-sync behavior.

### Acceptance
- [ ] Historical backlog entries no longer create new realtime `push_events`.
- [ ] `score` success triggers Miniflux read-sync attempts.
- [ ] Already `scored/verified/pushed` unread entries no longer rerun summary/score.
- [ ] Automated tests cover recent vs historical push gating and read-sync request shape.

### Risks & Rollback
- Risk: Existing recently scored-but-unpushed rows will be treated as terminal and only retried for read-sync, not retro-pushed.
- Rollback: Revert the workflow/activity changes and restore the previous `should_push + verify-before-gate` behavior if the new gating drops valid realtime alerts.

## 2026-03-17 Empty Content Quarantine

### Context
- Problem: Some Miniflux items return effectively empty content, which causes `summary` to fail before the workflow can reach `score -> mark read`. Because `failed` and `summarized` remain processable, the same low-value backlog items keep re-entering ingest and consuming the front of the unread window.
- Scope: Quarantine permanently empty-content entries on first detection, sync them back to Miniflux as `read`, and clean up debug visibility so stale `error` values no longer misrepresent successful rows.
- Constraints: Preserve backward compatibility with existing Temporal histories, keep public HTTP and Telegram interfaces unchanged, and avoid introducing a generic retry subsystem for all failure types.

### Decisions
- Decision 1: Add an explicit terminal `quarantined` entry status plus `quarantine_reason`, but only use it for `empty_content` in this change.
- Decision 2: Quarantined entries should retry only Miniflux read-sync on later ingest runs; they must not re-enter `summary`, `score`, `verify`, or `push`.

### Steps
1. Add `quarantined` state and `quarantine_reason` to the data model, debug schema, and migration layer.
2. Detect empty content during `fetch_and_upsert_entry_activity`, quarantine immediately, and return a non-processable ingest result.
3. Keep a fallback quarantine path in `summarize_entry_activity` for older in-flight workflows that already reached summary with empty content.
4. Clear sticky `entries.error` on successful summary/score/verification writes, add tests, and verify the new debug counters and recent-entry shape.

### Acceptance
- [x] Empty-content entries are quarantined before they re-enter the LLM pipeline on later ingest runs.
- [x] Quarantined entries only retry Miniflux read-sync and no longer consume summary/score capacity.
- [x] Debug overview exposes `quarantined_entries` and per-entry `quarantine_reason`.
- [x] Successful summary/score/verification writes clear stale `entries.error` values.

### Risks & Rollback
- Risk: Treating empty content as permanently quarantined could hide a source that later starts returning valid content under the same entry URL.
- Rollback: Revert the quarantine migration and activity/repository changes, then reprocess the affected unread entries manually if the quarantine policy proves too strict.

## Template

### Context
- Problem:
- Scope:
- Constraints:

### Decisions
- Decision 1:
- Decision 2:

### Steps
1. Step
2. Step

### Acceptance
- [ ] Condition 1
- [ ] Condition 2

### Risks & Rollback
- Risk:
- Rollback:
