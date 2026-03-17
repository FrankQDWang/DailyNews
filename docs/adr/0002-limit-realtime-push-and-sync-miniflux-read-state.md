# ADR 0002: Limit Realtime Push and Sync Miniflux Read State

- Status: Accepted
- Date: 2026-03-17

## Context
Production ingest was working, but the system still treated the entire Miniflux `unread` backlog as realtime push candidates. That caused historical articles to generate Telegram alerts long after publication and let the same backlog re-enter the LLM pipeline when Miniflux items stayed unread.

## Decision
Restrict realtime Telegram push eligibility to entries inside a fixed `PUSH_WINDOW_HOURS` window, defaulting to `24`. Entries outside that window still go through `ingest + summary + score` so they remain usable for RAG, but they no longer trigger `verify` or `push`.

After `score` succeeds, the workflow now attempts to mark the corresponding Miniflux entry as `read`. Read-sync failures are logged and retried on later ingest runs without rolling back the saved `summary` or `score`. Entries already in terminal local states (`scored`, `verified`, `pushed`) are no longer sent back through `summary`/`score`; later cron runs only retry the Miniflux read-sync.

## Alternatives Considered
- Keep current behavior and rely only on the daily push cap. Rejected because it still allows historical backlog spam and unnecessary LLM recomputation.
- Mark entries `read` immediately after ingest. Rejected because failed `summary`/`score` runs would remove the article from the queue before processing completed.
- Stop processing historical backlog entirely. Rejected because `/ask` and future ranking still benefit from historical `summary` and `score` data.

## Consequences
- Positive: Telegram realtime alerts become genuinely incremental instead of replaying backlog.
- Positive: Miniflux `unread` should decline as processing completes, reducing repeated work.
- Positive: Historical articles remain searchable because they still get summarized and scored.
- Negative: Existing rows already in terminal local states will only retry Miniflux read-sync; they will not be retro-pushed even if they are recent.

## Outcome
Implemented with a new `PUSH_WINDOW_HOURS` setting, Miniflux bulk read-sync integration, workflow gating changes, and unit tests for push-window eligibility and read-sync request handling.
