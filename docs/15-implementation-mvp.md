# 15 实现落地说明（Temporal + DeepSeek-only）

## 已实现范围

- FastAPI webhook 与命令路由（`/help /ask /top /digest /topic /read /deepdive`）
- Temporal 工作流骨架：
  - `IngestBatchWorkflow`
  - `ProcessEntryWorkflow`
  - `VerifyEntryWorkflow`
  - `PushAlertWorkflow`
  - `DailyDigestWorkflow`
  - `DeepDiveWorkflow`
- Miniflux 采集链路：refresh / unread / fetch-content / upsert
- L0/L1/L2：DeepSeek JSON 输出 + Pydantic 校验
- A 级推送、日报推送、基础限流、基于 Postgres 的 `update_id` 去重
- PostgreSQL/pgvector schema 与 Alembic 初始迁移
- CI guardrails：`ruff + mypy + pytest + forbid_uv_pip + repo contracts`
- Harness 基线：`AGENTS.md`、`PLANS.md`、PR 模板、每日实验快照 workflow

## 当前限制（MVP）

- `/ask` 的检索当前使用近期摘要优先策略，向量召回策略已留接口，后续接入真实 embedding 模型优化。
- `sendMessage` 采用单进程基础节流与重试策略，后续如需多实例强一致限流，可补数据库或专用限流层。
- `Temporal` 连接参数按环境变量驱动，当前支持本地或 Railway 自托管 Temporal。

## 本地验证命令

```bash
uv sync --dev
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic upgrade head
uv run python apps/worker/main.py
uv run python apps/api/run.py
```
