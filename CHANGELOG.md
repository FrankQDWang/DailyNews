# Changelog

## [Unreleased]

- Add `GET /internal/debug/overview` for internal operational snapshot checks.
- Limit realtime Telegram alerts to the recent push window and mark Miniflux entries as `read` after scoring.
- Quarantine permanently empty-content entries, expose quarantine state in debug overview, and stop retrying them through the LLM pipeline.
