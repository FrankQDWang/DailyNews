# 03 Miniflux（RSS 聚合层）配置与 API 使用

## 为什么用 Miniflux（而不是自己写 RSS 抓取）

- RSS/Atom 千奇百怪：编码、重定向、截断、反爬、失败重试
- 你真正的价值在“智能层”：总结、打分、核验、对话
- Miniflux 提供你需要的关键 API：
  - OPML 导入
  - 拉 unread entries
  - fetch-content 抓原文（解决 RSS 截断）

---

## 必用 API（实现时直接对照）

认证方式：
- 建议用 API Key；通过 HTTP Header `X-Auth-Token` 调用。  

### 1) OPML Import（导入 92 源）
- `POST /v1/import`
- Body: OPML XML
- 成功返回 201  

### 2) Refresh all Feeds（刷新订阅）
- `PUT /v1/feeds/refresh`
- 返回 204；后台刷新（无需等待）

### 3) Get Entries（拉 unread）
- `GET /v1/entries?status=unread&direction=desc`
- 支持各种 filters（limit, offset, category, …）

### 4) Fetch original article（抓原文）
- `GET /v1/entries/{entryID}/fetch-content?update_content=true`
- `update_content=true` 会把抓到的 title/content 写回 Miniflux DB

> 上述 endpoint/行为均来自 Miniflux 官方 API 文档；实现时以官方为准。  

---

## ingest 伪代码（cron-ingest）

1. `PUT /v1/feeds/refresh`
2. `GET /v1/entries?status=unread&direction=desc`
3. for each entry:
   - `GET /v1/entries/{id}/fetch-content?update_content=true`（可并发，但要限速）
   - 将 entry 的 title/url/content/published_at 等 upsert 到 assistant-db
   - enqueue worker: summarize(entry_id)
4. （可选）调用 `PUT /v1/entries` 批量把已处理的 entry 标记为 read（避免重复拉取）

---

## 注意事项

- fetch-content 返回 HTML，你需要抽取纯文本用于 embedding 与 prompt（建议同时保存 HTML 和 text）
- 对于付费墙/强反爬网站：Miniflux 抓不到全文就保留 RSS 内容，L0 仍可摘要，但置信度下调
- Miniflux/assistant 之间最好走 Railway 私网，不要暴露 Miniflux API 到公网
