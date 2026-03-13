# 13 给 Codex 的可执行 Backlog（按顺序实现）

> 目标：让 Codex 5.3 直接照做，能逐步交付可运行系统。  
> 每个任务都包含：Goal / Output / Steps / Acceptance。

---

## T00 Repo & Local Dev Skeleton

**Goal**
- 建一个 monorepo，支持本地 docker-compose 一键启动（便于开发），同时可拆成 Railway 多服务部署。

**Output**
- repo 目录结构
- docker-compose.dev.yml
- .env.example
- makefile（可选）

**Acceptance**
- 本地 `docker compose up` 能跑起：assistant-db、temporal、miniflux（可选）

---

## T01 assistant-db schema + migrations

**Goal**
- 建立 05-data-model.md 的表结构 + 索引 + enum

**Output**
- migrations（Alembic/Prisma/…）
- 初始 schema
- seed script（可选）

**Acceptance**
- `migrate up` 成功
- 能插入 entry + summary + score，并通过 unique 约束防重复

---

## T02 Deploy Miniflux + Import OPML

**Goal**
- Railway 上跑 Miniflux + miniflux-db，能导入 92 源

**Output**
- Railway service 配置说明（写进 docs 或脚本）
- OPML 导入脚本：`scripts/import_opml.py`

**Acceptance**
- Miniflux UI 能看到 feeds
- API token 可用
- `GET /v1/entries?status=unread` 有数据

---

## T03 Miniflux client module

**Goal**
- 写一个 `miniflux_client`，封装：
  - refresh feeds
  - list unread entries
  - fetch-content
  - mark entries read（可选）

**Acceptance**
- 单元测试或简单脚本跑通

---

## T04 cron-ingest job

**Goal**
- 实现每 10 分钟：
  - refresh -> list unread -> fetch-content -> upsert assistant-db -> enqueue summarize

**Acceptance**
- 重复跑不会重复入库（幂等）
- 单条失败不影响整体
- job 执行完能 exit（否则 Railway cron 会跳过后续）

---

## T05 Workflow + Worker skeleton

**Goal**
- 定义 Temporal task queues：
  - summarize_l0
  - score_l1
  - verify_l2
  - embed_chunks
  - push_send
  - digest_build
  - deepdive

**Acceptance**
- worker 能取任务并写日志

---

## T06 L0 summarizer

**Goal**
- 实现 L0 prompt（07-prompts.md）
- 保存 summaries 表
- 更新 entries.status

**Acceptance**
- 对一篇文章产出结构化 JSON
- 失败重试，最终失败写入 failed 状态

---

## T07 L1 scorer + grade

**Goal**
- 实现 L1 prompt + rubric（08-ranking-rubric.md）
- 写 scores 表
- 根据 grade 决定是否 enqueue L2 / push

**Acceptance**
- 能产出 A/B/C
- A 级自动入 L2 队列

---

## T08 L2 verifier (A only)

**Goal**
- 实现最小核验：
  - 抽 claims
  - 优先抓文章引用链接
  - 可选：用 search provider 补证据
- 写 verifications 表

**Acceptance**
- 对 A 级文章能产出 verdict/confidence/evidence
- 如果核验失败，A 级消息必须标注未核验或降级

---

## T09 Telegram sender + rate limiter

**Goal**
- 实现 push_send worker
- token bucket：群 20 msg/min + 单 chat 1 msg/sec
- 文本分片（<=4096）

**Acceptance**
- 压测 30 条消息不会 429（或能正确 retry）
- 长文本自动分多条发送且顺序正确

---

## T10 Telegram webhook + command router

**Goal**
- assistant-api 实现：
  - webhook endpoint
  - update_id 去重
  - 命令路由：/help /ask /top /digest /topic /read /deepdive

**Acceptance**
- 群里任意成员 `/ask` 能得到回复
- `/top 24h` 能列出条目

---

## T11 RAG for /ask

**Goal**
- entry_chunks 生成（chunk + embedding）
- /ask 用 pgvector 检索 top-k chunks
- 回复包含 sources 列表

**Acceptance**
- 对 “最近一周 Agents 有什么趋势？” 能回答并给引用

---

## T12 Daily digest job（07:00 北京时间）

**Goal**
- cron-digest：窗口=last_digest_at..now
- 生成 report_json + 渲染 markdown
- 推送到群

**Acceptance**
- Railway cron 设 `0 23 * * *`（UTC）能每天发
- 报告包含 Top/分组/趋势/建议

---

## T13 Feedback loop

**Goal**
- 支持 `/feedback <id> up|down` 或按钮
- 反馈影响后续权重（08-ranking-rubric.md 的闭环规则）

**Acceptance**
- 点赞后同主题后续更容易上榜（可用简单模拟验证）

---

## T14 Observability + Runbook

**Goal**
- 添加 metrics/logs
- 写运行手册

**Acceptance**
- 任一阶段失败能定位原因
- 有 retry/backoff

---

## T15 Hardening（安全/注入/滥用）

**Goal**
- prompt injection 防护
- per-user rate limit
- admin allowlist

**Acceptance**
- 群里有人刷 /ask 不会打爆成本（触发 rate limit）
- 恶意文章内容不会让 bot 泄露 secrets
