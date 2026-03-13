# 12 可观测性与 Runbook

## 指标（Metrics）

建议至少这些（Prometheus 或 Railway logs 统计都行）：

- ingest:
  - ingest_runs_total / ingest_runs_failed
  - new_entries_found
  - miniflux_fetch_content_failures
- worker:
  - tasks_total{type=l0|l1|l2|embed|digest|push}
  - task_latency_ms p50/p95
  - llm_errors_total / llm_retry_total
- telegram:
  - messages_sent_total
  - telegram_429_total
  - send_latency_ms
- queue:
  - queue_depth{queue=...}

## 日志（Logs）

统一结构化日志字段：
- trace_id / correlation_id
- entry_id / miniflux_entry_id
- job_type
- duration_ms
- error_stack

## Runbook（常见故障处理）

### 1) cron 没按时跑 / 频繁跳过
- 看 Railway cron service 状态是否还 Active
- 检查代码是否有未关闭连接/未退出
- 把重活挪到 worker（cron 只入队）

### 2) Telegram 429
- 检查 sender 是否节流
- 降低 burst：A 级推送入队后按 1 msg/sec 发
- 长消息拆分更细

### 3) 某些网站抓不到全文
- 允许降级：仅用 RSS 摘要做 L0
- 标记 risk_flags=paywall/partial_content
- 对这种源整体降权

### 4) LLM 输出非 JSON
- 强制 JSON 模式/函数调用（如果 provider 支持）
- 失败重试 2 次后落失败队列
- 允许手动 `/reprocess <id>`

### 5) DB 膨胀
- 清理策略：保留窗口内 chunk，旧 chunk 可删
- 报表与 summary 长期保留
