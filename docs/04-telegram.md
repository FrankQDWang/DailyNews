# 04 Telegram Bot：Webhook、隐私模式、限流、消息模板

## 更新接入：Webhook（Railway 适配）

Telegram 提供两种互斥方式收 updates：`getUpdates`（long polling）与 `setWebhook`。  
在 webhook 设置存在时，不能再用 long polling 获取更新。  

建议：Railway 上用 Webhook。

### Webhook 基本要求（官方）
- 需要 HTTPS（TLS 1.2+）
- 端口必须是 443/80/88/8443 之一
- 证书 CN/SAN 需匹配域名
- 支持 IPv4（官方说明 IPv6 webhook 目前不支持）  

Railway 默认给你 HTTPS domain（443），通常不需要自己管证书。

### Webhook 安全建议
- 使用“秘密路径”：`/telegram/webhook/<secret>`
- 额外校验：请求 header + secret（可选）

---

## 群消息接收策略（privacy mode）

你希望“允许所有成员提问”，但不建议 bot 监听全群自然语言（成本高、噪声大）。

推荐做法：
- 保持 privacy mode 开启
- 规定交互方式：`/ask ...` 或 `@bot ...` 或 回复 bot 的消息

官方说明（简化）：
- privacy mode 启用时，bot 会接收显式给它的命令、回复、@它等消息
- 关闭 privacy mode 或把 bot 设为管理员，会收到更多消息  

---

## 发送限制（必须写节流）

Telegram 官方建议：
- 在单个 chat：不要超过 1 msg/sec（否则会 429）
- 在群里：每群不超过 20 msg/min
- 广播到大量 chat：约 30 msg/sec（需要付费广播才能更高）  

因此必须实现：
- push 队列
- token bucket / leaky bucket
- 失败重试（遇 429 读取 retry-after）

---

## 消息长度限制与分片

sendMessage 的 text 字段限制：**1–4096 characters**（实体解析后）。  
实现必须支持“自动分片发送”，并且：
- 分片不要切断 Markdown/HTML tag（否则 parse_mode 解析失败）
- 建议统一用 MarkdownV2 或 HTML（择一），并实现 escape

---

## 命令设计（群里所有成员可用）

必备：
- `/help`：帮助
- `/ask <问题>`：研究助理问答（RAG）
- `/top 24h`：最近 24 小时 Top
- `/digest`：最近一次日报/今天摘要
- `/topic agents|eval|product|engineering|biz`
- `/read <id>`：读某条的摘要
- `/deepdive <id>`：触发深挖（可能较慢）

管理员命令（仅 allowlist）：
- `/config`（展示当前配置）
- `/set <key> <value>`（可选，动态调整）
- `/reindex`（重建 embedding/索引）

---

## A 级快讯模板（示例）

【A】<Title>
- 要点1
- 要点2
- 要点3
为什么重要：<1-2句，面向 AI 产品经理>

评分：A | 置信度：0.82
主题：Agents, Eval
链接：<url>
ID：E12345

日报模板、对话模板见 `10-chat-and-commands.md`。
