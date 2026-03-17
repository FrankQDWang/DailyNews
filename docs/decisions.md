# Decisions

2026-03-16 | Add an internal debug overview endpoint for operational state verification | [ADR 0001](docs/adr/0001-add-internal-debug-overview.md)
2026-03-17 | Limit realtime push to a 24-hour window and sync Miniflux read state after scoring | [ADR 0002](docs/adr/0002-limit-realtime-push-and-sync-miniflux-read-state.md)
2026-03-17 | Quarantine permanently empty-content entries and retry only Miniflux read-sync | [ADR 0003](docs/adr/0003-quarantine-empty-content-entries.md)
2026-03-17 | Add explicit verification audit state and reasoned push gating | [ADR 0004](docs/adr/0004-add-verification-audit-state.md)
2026-03-17 | Reduce Miniflux fetch churn, cap ingest fan-out, and add LLM usage telemetry | [ADR 0005](docs/adr/0005-reduce-fetch-churn-and-add-llm-usage-telemetry.md)
2026-03-17 | Move unread batch preparation into an activity to eliminate oversized Temporal ingest payloads | [ADR 0006](docs/adr/0006-shift-ingest-batch-preparation-into-activity.md)
2026-03-17 | Treat deferred fetches and quarantine exits as successful process outcomes instead of workflow failures | [ADR 0007](docs/adr/0007-stop-counting-expected-process-exits-as-workflow-failures.md)
2026-03-17 | Adopt balanced ingest defaults of scan 200 / process 15 to align repository baselines with production cost tuning | [ADR 0008](docs/adr/0008-adopt-balanced-ingest-defaults-for-production.md)
