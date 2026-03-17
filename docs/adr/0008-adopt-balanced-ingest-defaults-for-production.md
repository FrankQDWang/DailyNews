# ADR Template

- Status: Accepted
- Date: 2026-03-17

## Context

Production cost tuning on Railway showed that the main controllable API and worker-cost lever was the number of entries allowed into each ingest run, not the API service itself. Production was manually tuned to `MINIFLUX_SCAN_LIMIT=200` and `INGEST_ACTIONABLE_LIMIT=15`, but repository defaults still pointed to `300/30`, which created drift between fresh deployments and the tuned production baseline.

## Decision

Adopt `MINIFLUX_SCAN_LIMIT=200` and `INGEST_ACTIONABLE_LIMIT=15` as the repository defaults in `Settings` and `.env.example`.

## Alternatives Considered

- Keep repository defaults at `300/30` and rely on Railway environment variables only.
- Reduce defaults further to a more aggressive throttle such as `100/10`.
- Change only the cron schedule and leave per-run batch defaults unchanged.

## Consequences

- New environments now inherit the lower-cost balanced ingest baseline even before service-specific overrides are added.
- Backlog drain rate slows compared with `300/30`, but worker CPU, Miniflux fetch churn, and LLM call volume are reduced.
- This does not change existing production services unless their environment variables are absent or updated.

## Outcome

Accepted.
