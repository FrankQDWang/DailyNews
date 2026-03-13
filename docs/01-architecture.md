# 01 架构与数据流（Railway 版）

## 服务清单（Railway Project 内）

1) **miniflux-db**（Postgres）
2) **miniflux**（RSS 聚合器）
3) **assistant-db**（pgvector Postgres，存你的摘要/embedding/对话状态）
4) **temporal**（Workflow engine）
5) **temporal-db**（Temporal persistence，Postgres）
6) **assistant-api**（Webhook + 对话 + 查询）
7) **assistant-worker**（总结/打分/核验/embedding）
8) **cron-ingest**（每 10 分钟：刷新 + 拉取新条目 + 入队；跑完退出）
9) **cron-digest**（每天 07:00 北京时间：生成日报；跑完退出）

> Railway cron 的要求：cron 服务**必须执行完就退出**；如果上一次仍 Active，下一次会被跳过；cron 基于 UTC，最短间隔 5 分钟。见官方文档引用（在本包末尾“参考链接”里）。  

---

## 数据流（从 RSS 到群消息）

```
[92 RSS/Atom Sources]
        |
        v
   (Miniflux refresh)
        |
        v
[Miniflux Entries (unread)]
        |
        v
 cron-ingest:
   - 拉 unread
   - fetch-content 抓全文
   - 写 assistant-db
   - enqueue summarize task
        |
        v
 assistant-worker pipeline:
   L0 总结 -> L1 打分/标签 -> (A级) L2 核验 -> 入库
        |
        +--------------------+
        |                    |
        v                    v
  A级快讯推送            每日 Digest 生成
        |                    |
        +----------+---------+
                   v
            Telegram 群（Bot）
                   |
                   v
            /ask /topic /top /deepdive
                   |
                   v
              assistant-api (RAG)
```

---

## 关键设计点（避免踩坑）

### 1) “cron 只做轻量触发”，重活交给 worker
原因：Railway cron 运行时，如果代码没退出，下次会跳过。大模型慢、外部请求慢，放 cron 里风险高。

### 2) 推送必须排队 + 节流
Telegram 群发送限制较严格（每群 20 条/分钟）。必须对 sendMessage 做队列与 token bucket。

### 3) A 级推送应“核验后再发”
否则群里会被错误信息污染。代价是延迟上升，但 A 级数量上限 10/天，完全可接受。

### 4) 对话上下文按 (chat_id, user_id) 隔离
避免群里多人提问互相串线。
