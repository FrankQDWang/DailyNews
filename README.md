# RSS Research Assistant（Telegram 对话式研究助理）实施计划（可交给 Codex 执行）

你要做的是：**监控 92 个博客（RSS/Atom）→ 全量抓取/去重 → L0 总结 + L1 重要性分级 → A 级自动核验（L2）→ Telegram 群推送（A 级快讯 + 每日 Digest）→ 群内可对话问答（RAG + 可触发深挖）**。

本套文档默认满足你给定的偏好：

- **日报时间：北京时间 07:00**
- **允许群里所有成员提问**
- **输出语言：中文为主，夹英文术语**
- **A 级快讯每日上限：10 条**
- **重点主题：Agents / Eval / 产品策略 / 工程化落地 / 创业与商业化**
- **A 级默认自动核验**

---

## 这份文档包包含什么？

- 设计目标与产品形态：`docs/00-overview.md`
- 架构与数据流：`docs/01-architecture.md`
- Railway 部署（含 cron 时区换算）：`docs/02-railway-deployment.md`
- Miniflux（RSS 聚合层）配置与 API：`docs/03-miniflux.md`
- Telegram Bot（Webhook、隐私模式、限流、命令）：`docs/04-telegram.md`
- 数据库与表结构（含向量检索）：`docs/05-data-model.md`
- 处理流水线（ingest → summarize → score → verify → push）：`docs/06-pipeline.md`
- Prompts/JSON schema：`docs/07-prompts.md`
- 重要性分级 Rubric（含权重）：`docs/08-ranking-rubric.md`
- A 级核验 Agent 设计：`docs/09-verification-agent.md`
- 对话（RAG）与命令交互规格：`docs/10-chat-and-commands.md`
- 安全与抗 Prompt Injection：`docs/11-security.md`
- 可观测性与 Runbook：`docs/12-observability-runbook.md`
- **给 Codex 的可执行 Backlog（按顺序做即可）：`docs/13-codex-backlog.md`**
- 开放问题清单（可晚点再决定）：`docs/14-open-questions.md`
- 当前实现落地说明（Temporal + DeepSeek-only）：`docs/15-implementation-mvp.md`

---

## 最推荐的 MVP 路线（先跑起来再增强）

1. 在 Railway 起 Miniflux + Postgres（订阅层稳定）
2. 起 Telegram webhook 服务（/help、/ask、/digest 先可用）
3. 起 ingest cron：刷新 feed → 拉 unread → 抓全文 → 入库 → 入队
4. 起 worker：L0 总结 + L1 打分 + A 级推送（先不做核验也行）
5. 起每日 digest cron：07:00 北京时间推送（含 Top + 分组）
6. 再加：A 级自动核验、RAG 对话、反馈闭环、可观测性

---

> 注：当前代码骨架已落地为 Python（FastAPI + Temporal + Postgres/pgvector）。
> 当前仓库以 Railway 部署为主，`.env.example` 使用 Railway-first 占位值；如果只做本地烟测，请自行改成 localhost/dev 地址。

---

## 当前实现状态（2026-03-05）

已落地基础骨架（Temporal + DeepSeek-only）：

- `apps/api`：FastAPI webhook、命令路由、health/ready/metrics、internal reprocess
- `apps/worker`：Temporal worker（ingest/process/verify/push/digest/deepdive 队列）
- `apps/jobs_ingest`：Railway cron 触发 Ingest workflow（触发后退出）
- `apps/jobs_digest`：Railway cron 触发 Digest workflow（触发后退出）
- `libs/core`：配置、DB model/repository、schema、限流、基于 Postgres 的 webhook 去重、指标
- `libs/integrations`：DeepSeek/Miniflux/Tavily/Telegram client
- `libs/workflows`：Temporal workflows + activities
- `migrations`：Alembic 初始迁移
- `.github/workflows/ci.yml`：lint/type/test + 禁用 `uv pip`
- `scripts/forbid_uv_pip.sh`：扫描并阻断 `uv pip`
- `AGENTS.md` / `PLANS.md`：Harness 工程规范入口

## 本地烟测（可选）

1. 启动依赖

```bash
docker compose -f docker-compose.dev.yml up -d
```

2. 配置环境变量

```bash
cp .env.example .env
```

3. 安装依赖与迁移

```bash
uv sync --dev
uv run alembic upgrade head
```

4. 启动服务

```bash
uv run python apps/worker/main.py
uv run python apps/api/run.py
```

5. 触发任务

```bash
uv run python apps/jobs_ingest/main.py
uv run python apps/jobs_digest/main.py
```
