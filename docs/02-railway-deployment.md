# 02 Railway 部署计划（服务拆分 + cron 时区换算）

## Railway 事实约束（需要写进实现里）

- Cron 基于 UTC，且**最短间隔不能小于 5 分钟**。
- Cron 任务要求：执行完必须退出；如果上一轮仍在运行，下一次会被跳过；Railway 不会自动 kill。  
- Postgres 服务会提供 `DATABASE_URL` 以及 PGHOST/PGPORT/… 等变量给同项目服务引用。  

（上面三条都来自 Railway 官方文档链接，见 `README` 末尾引用。）

---

## 服务与部署形态

### 1) miniflux-db（Postgres）
- Railway 官方 Postgres service
- 仅用于 Miniflux

### 2) miniflux（Docker image 或源码构建）
- 环境变量指向 miniflux-db 的 `DATABASE_URL`
- 暴露 web UI（可选），但至少要能从内部网络被 cron-ingest 调用 API

### 3) assistant-db（pgvector Postgres）
- 建议用 Railway marketplace 的 pgvector 模板（而不是默认 Postgres）
- 表：entries、chunks、summaries、scores、reports、conversations、feedback…

### 4) temporal
- 生产建议使用 `temporalio/server` 镜像部署 workflow service
- 不要直接把本地 smoke 用的 `temporalio/auto-setup` 当成 Railway 生产镜像
- 持久化存储指向 temporal-db（Postgres）

### 5) temporal-db
- Railway Postgres service
- 仅供 Temporal 持久化使用

### 6) assistant-api（常驻）
- 负责 Telegram webhook 接入与 `/ask`、`/digest`、`/topic` 等命令
- 暴露一个 HTTPS endpoint（Railway 会给 domain），供 Telegram setWebhook

### 7) assistant-worker（常驻）
- 监听 Temporal task queues
- 跑 L0/L1/L2、embedding、推送队列

### 8) cron-ingest（Cron Job service）
- Start command: `uv run python apps/jobs_ingest/main.py`
- Cron: `*/10 * * * *`（每 10 分钟）
- 任务逻辑：刷新 miniflux -> 拉 unread -> fetch-content -> upsert assistant-db -> 启动 workflow

### 9) cron-digest（Cron Job service）
- Start command: `uv run python apps/jobs_digest/main.py`
- **北京时间 07:00 = UTC 23:00（前一日）**
- Cron: `0 23 * * *`
- 任务逻辑：从 assistant-db 查窗口 -> 生成 digest -> 发 Telegram -> 更新 last_digest_at

> 说明：Railway cron 使用 UTC，需要你自己换算时区。  

---

## 环境变量（建议标准化）

### 共同（assistant-api / worker / cron）
- `ASSISTANT_DB_URL`：pgvector Postgres 的 `DATABASE_URL`
- `MINIFLUX_BASE_URL`
- `MINIFLUX_API_TOKEN`（Miniflux 的 X-Auth-Token）
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_TARGET_CHAT_ID`（你的群 chat_id）
- `TELEGRAM_WEBHOOK_SECRET`（自定义字符串，用于 webhook path 或 header 校验）
- `TEMPORAL_HOST`
- `TEMPORAL_NAMESPACE`

### LLM（当前实现为 DeepSeek-only）
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `LLM_MODEL_SUMMARY`（L0）
- `LLM_MODEL_SCORE`（L1）
- `LLM_MODEL_VERIFY`（L2）
- `LLM_MODEL_CHAT`（对话）

### 运行参数
- `A_PUSH_LIMIT_PER_DAY=10`
- `LANGUAGE_MODE=zh_with_en_terms`
- `FOCUS_TOPICS=agents,eval,product,engineering,biz`
- `RATE_LIMIT_USER_QPM=6`（示例：每用户每分钟 6 次）
- `RATE_LIMIT_CHAT_QPM=60`（示例：全群每分钟 60 次）

---

## Railway “多服务同仓库”建议

- Monorepo：`/apps/api`、`/apps/worker`、`/apps/jobs_ingest`、`/apps/jobs_digest`
- 每个 service 配独立 Start Command 或独立 Dockerfile（任选其一）
- 变量用 Service Variables；需要跨服务引用时用 Reference Variables（Railway 文档有说明）
