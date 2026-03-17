# ADR 0003: Quarantine Empty Content Entries

- Status: Accepted
- Date: 2026-03-17

## Context
Production ingest still wasted capacity on a class of Miniflux items whose fetched content was effectively empty, for example `<p></p>`. Those rows could fail before `score`, which meant the workflow never reached the existing Miniflux `mark read` step. Because `failed` and `summarized` rows remained processable, the same items kept re-entering ingest and crowding out useful unread entries. The debug snapshot also kept stale `error` values on rows that had later progressed successfully, which made operational state harder to trust.

## Decision
Introduce an explicit terminal `quarantined` entry status and a nullable `quarantine_reason` field. When ingest sees content that normalizes to empty text, it quarantines the entry immediately with `quarantine_reason = "empty_content"`, clears `error`, and attempts to mark the Miniflux entry as `read`. Quarantined rows never re-enter `summary`, `score`, `verify`, or `push`; later ingest runs only retry the Miniflux read-sync if the item is still unread.

The same change also clears stale `entries.error` values whenever `summary`, `score`, or `verification` succeeds, and extends the internal debug overview to expose `quarantined_entries` plus each recent entry's `quarantine_reason`.

## Alternatives Considered
- Keep using `failed` for empty content and rely on retries. Rejected because it guarantees repeated ingest churn for permanently empty source items.
- Add a generic retry-budget or dead-letter system for every failure mode. Rejected because the immediate problem is narrow and permanent; a broader retry framework would add more surface area than needed for this fix.
- Mark empty-content items `read` without a local terminal status. Rejected because Miniflux read-sync can fail independently, and the local database still needs a durable signal to avoid rerunning LLM work.

## Consequences
- Positive: Empty-content backlog items stop consuming the ingest window after first detection.
- Positive: Later ingest runs can still clean up unread state in Miniflux without re-entering the LLM pipeline.
- Positive: Debug output becomes less noisy because successful rows clear stale `error` values and quarantined rows are explicit.
- Negative: An entry quarantined for empty content will stay excluded even if a publisher later fixes the article body; recovering such cases now requires manual intervention.

## Outcome
Implemented with a new `quarantined` enum value, `entries.quarantine_reason`, quarantine-aware ingest activities, sticky-error cleanup in repository success paths, debug overview schema changes, and unit tests for empty-content detection and quarantine behavior.
