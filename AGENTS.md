# DailyNews AGENTS Guide

## Working mode
- This repository follows Harness Engineering.
- Complex tasks must start from `PLANS.md` before implementation.

## Python toolchain
- Use `uv` for dependency management and execution.
- Do not use `uv pip` in any script, docs, or CI.

## Commands
- Sync: `uv sync --dev`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Type check: `uv run mypy .`
- Migrate: `uv run alembic upgrade head`

## Architecture constraints
- Runtime: FastAPI + Temporal + PostgreSQL/pgvector + Miniflux + Telegram webhook.
- Deploy target: Railway-first. Local docker-compose is optional smoke testing only.
- LLM provider is fixed to DeepSeek-only in MVP.
- A-grade verification: citation-first + Tavily fallback.
