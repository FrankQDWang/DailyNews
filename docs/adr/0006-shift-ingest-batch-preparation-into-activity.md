# ADR 0006: Shift Ingest Batch Preparation Into Activity

- Date: 2026-03-17
- Status: Accepted

## Context

`scan 300 / process 30` reduced intended ingest fan-out, but the first implementation passed 300 serialized unread entries through `IngestBatchWorkflow`. In production this created a Temporal payload of about 2.8 MB and triggered `PayloadSizeWarning`, which stopped the ingest chain after unread listing.

We need to preserve the resource-optimization policy while removing the oversized workflow payload and improving observability for each ingest batch.

## Decision

- Add `prepare_ingest_batch_activity(scan_limit, actionable_limit)` as the single place that fetches unread metadata, performs metadata-only upserts, classifies entries, and batches Miniflux read-sync for terminal or blocked rows.
- Restrict `IngestBatchWorkflow` to orchestration only: `refresh -> prepare batch -> start child workflows` using only actionable `entry_id`s.
- Persist the latest batch summary in `ingest_batch_runs` and expose it via `/internal/debug/overview.latest_ingest_batch`.
- Keep `fetch_and_upsert_entry_activity` registered for Temporal compatibility, but stop using it from the current ingest workflow.

## Consequences

### Positive
- Eliminates the large unread payload from the Temporal workflow boundary.
- Keeps `fetch-content` on the on-demand summary path, so automatic ingest only starts it for actionable entries.
- Gives production validation a durable per-batch snapshot instead of depending on logs alone.

### Negative
- Introduces a small new table, `ingest_batch_runs`.
- Batch read-sync now happens inside the batch preparation activity, so failures there need dedicated logging and validation.
