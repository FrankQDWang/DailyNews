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
