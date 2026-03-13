# 06 流水线设计（ingest → summarize → score → verify → push → digest → chat）

## Step 0：Ingest（cron-ingest）

输入：Miniflux unread entries  
输出：assistant-db entries + tasks

关键点：
- cron 只做轻量 IO 与入队，不跑 LLM
- 幂等：miniflux_entry_id/url 唯一约束

流程：
1. refresh feeds
2. list unread entries
3. fetch-content（可选但推荐）
4. upsert entry（写 HTML+Text）
5. enqueue: `summarize(entry_id)`

失败处理：
- 单条失败不影响整批
- 写 `entries.status=failed` + error 字段（可单独补偿重跑）

---

## Step 1：L0 总结（worker）

输入：entry.content_text  
输出：summaries

要求：
- 输出结构化 JSON（schema 见 prompts）
- 语言：中文为主 + 英文术语
- 对“信息不完整/疑似付费墙”要显式提示并下调置信度

---

## Step 2：L1 重要性评分（worker）

输入：L0 summary_json + title + tags  
输出：scores

要求：
- 重点主题维度打分：Agents/Eval/Product/Engineering/Biz
- 产出 grade A/B/C + 理由（1–2 句）
- overall 为加权分（权重见 ranking rubric）

---

## Step 3：A 级 L2 核验（worker）

触发条件：grade==A  
输入：entry + L0 + L1  
输出：verifications

最小核验（MVP）：
- 从文章中抽取 3–7 个关键主张（claims）
- 优先验证：
  - 是否有引用链接（论文/官方文档/Repo）
  - 如果有：抓取引用页面标题/摘要/关键句（避免长引用）
  - 如果没有：用 Tavily 找 1–3 个高质量来源佐证/反证
- 输出：verified / partially_verified / uncertain + 证据列表 + 置信度

---

## Step 4：推送（worker → push queue）

### A 级快讯推送规则
- 仅当 L2 完成（或 L2 超时降级为“未核验 A-”并在消息中标注）
- 每天上限 10 条：超过进入日报，不再实时推送
- 消息入 push_queue，由 sender 统一节流发送

### Telegram sender（建议独立 worker）
- 从 push_queue 取消息
- 进行：
  - 长度切分（<=4096）
  - parse_mode escape
  - token bucket 节流（群 20 msg/min + 单 chat 1 msg/sec）
- 发送成功写 push_events；失败重试（429 读取 retry-after）

---

## Step 5：每日 Digest（cron-digest）

触发：北京时间 07:00  
输入：window 内所有 entries + summaries + scores + (verifications)  
输出：daily_reports + Telegram 推送

策略：
- Top 5：按 overall 分数排序（A 优先）
- 主题分组：LLM 聚类 + label（也可用 embedding 聚类）
- 趋势雷达：统计 tags/entities 频次
- 建议：产出 3 个可执行动作（实验/产品/工程/商业）

---

## Step 6：对话式问答（assistant-api）

### /ask
- 检索：
  - query embedding
  - top-k chunks (pgvector)
  - + top-k entries 的 summary
- 生成：
  - 先回答
  - 再给“引用条目列表”（title + url + id）
  - 如果用户追问“核验”，则触发 deepdive/verify

### /deepdive <id>
- 如果该 entry 已 verified：直接输出核验结论 + 产品启示
- 否则：enqueue deepdive job；完成后 bot @用户回复结果
