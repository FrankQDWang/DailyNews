# 10 对话与命令交互规格（群内研究助理）

## 基本原则

- 所有成员可提问
- 对话状态按 (chat_id, user_id) 隔离
- 默认“只响应命令或 @bot / 回复 bot”，避免噪声与成本爆炸
- 长回复自动分片（每条 <= 4096 chars）

---

## 命令规格

### /help
输出：
- 简短说明 + 命令列表 + 示例

### /ask <question>
流程：
1) 解析意图（问趋势/对比/建议/查某条）
2) RAG 检索：top-k chunks + summaries
3) 生成回答（中文为主）
4) 返回 sources 列表（最多 5）
5) 给 followups 建议

### /top <6h|24h|7d>
- 从 DB 按 overall 排序取 top N（默认 10）
- 输出：title + why + link + id

### /digest [latest|today|yesterday]
- latest：最近一次日报（从 daily_reports）
- today/yesterday：按窗口重新生成或读缓存（可选）

### /topic <agents|eval|product|engineering|biz>
- 按 tags 或 scores.relevance_* 阈值过滤
- 输出：最近 N 条

### /read <id>
- 输出 L0 总结 + L1 评分 + 若有 L2 核验则附上
- 提供按钮/提示：`/deepdive <id>`

### /deepdive <id>
- enqueue deepdive job
- 立即回复：已开始深挖（给预计完成方式：完成后 @用户；不要承诺时间）
- 完成后推送：核验结果 + 产品启示

---

## 输出模板（建议统一风格）

### /ask 回复
【回答】
...

【依据（最近资料）】
1) <Title>（ID: E123）<url>
2) ...

【你可以继续问】
- ...
- ...

### /top
最近 24h Top 10：
1) [A|B] Title — why重要（ID）<url>
...

### /digest
📌 日报（窗口：...）
Top 5：
- ...
主题分组：
- Agents：...
趋势雷达：...
建议：...

---

## 成本与滥用防护（强烈建议）

- per-user：每分钟 6 次 /ask（可配置）
- per-chat：每分钟 60 次 /ask（可配置）
- 如果超限：提示稍后再试
- 对高成本操作（/deepdive）：每用户每天 5 次（可配置）
