# Changelog

## [Unreleased]

- Add `GET /internal/debug/overview` for internal operational snapshot checks.
- Limit realtime Telegram alerts to the recent push window and mark Miniflux entries as `read` after scoring.
- Quarantine permanently empty-content entries, expose quarantine state in debug overview, and stop retrying them through the LLM pipeline.
- Add verification audit state, backfill historical scored rows, and expose push-gate reasons plus recent A-grade candidates in the internal debug snapshot.
- Make ingest metadata-first, add fetch cooldown/block state plus `too_short_content` quarantine, cap each ingest run to `scan 300 / process 30`, and record per-task LLM token usage in the debug snapshot and Prometheus metrics.
- Move unread metadata processing into a dedicated batch activity, persist `latest_ingest_batch`, and remove the large unread payload from the Temporal workflow boundary.
- Set `ProcessEntryWorkflow` child launches to `ParentClosePolicy.ABANDON` so completed ingest batches no longer terminate in-flight process children.
- Add process-outcome audit fields and a preflight content-preparation activity so `cooldown/blocked` fetch deferrals and `empty_content/too_short_content` quarantines stop showing up as Temporal workflow failures.
