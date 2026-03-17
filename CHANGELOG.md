# Changelog

## [Unreleased]

- Add `GET /internal/debug/overview` for internal operational snapshot checks.
- Limit realtime Telegram alerts to the recent push window and mark Miniflux entries as `read` after scoring.
- Quarantine permanently empty-content entries, expose quarantine state in debug overview, and stop retrying them through the LLM pipeline.
- Add verification audit state, backfill historical scored rows, and expose push-gate reasons plus recent A-grade candidates in the internal debug snapshot.
- Make ingest metadata-first, add fetch cooldown/block state plus `too_short_content` quarantine, cap each ingest run to `scan 300 / process 30`, and record per-task LLM token usage in the debug snapshot and Prometheus metrics.
