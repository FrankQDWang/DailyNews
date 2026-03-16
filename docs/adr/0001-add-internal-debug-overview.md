# ADR 0001: Add Internal Debug Overview Endpoint

- Status: Accepted
- Date: 2026-03-16

## Context
Production verification still depended too heavily on Railway logs. That made it harder to confirm whether `ingest`, `summary`, `score`, `verification`, `push`, and Telegram webhook dedupe had actually persisted to Postgres.

## Decision
Add a read-only internal HTTP endpoint, `GET /internal/debug/overview`, protected by the existing `x_internal_token + x_admin_user_id` header pair. The endpoint returns fixed-shape JSON with key table counts and the latest five rows for the operational tables needed during debugging.

## Alternatives Considered
- Keep relying on Railway logs only. Rejected because it is indirect and incomplete for state validation.
- Add a Telegram admin debug command. Rejected for v1 because HTTP is simpler and safer to constrain.
- Expose a generic query interface. Rejected because the operational need is narrow and fixed-shape responses reduce leak risk.

## Consequences
- Positive: Operators can verify state directly from the API without depending on log completeness.
- Positive: Internal auth logic is now shared instead of duplicated across endpoints.
- Negative: The API surface grows by one internal route that must stay locked behind admin headers.

## Outcome
Implemented in `assistant-api` with repository-backed snapshot queries and automated route/repository tests.
