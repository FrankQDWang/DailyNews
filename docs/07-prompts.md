# 07 Prompts 与 JSON Schema（给 Codex 直接实现）

> 原则：**全部模型输出都要求 JSON**（严格 schema），再由代码渲染成 Telegram 文本。

---

## L0：结构化总结（Summarize）

### 输入
- title
- url
- published_at
- content_text（可能很长，建议先做 chunk + map-reduce 或 extractive）

### 输出 JSON Schema（示例）
```json
{
  "language": "zh_with_en_terms",
  "tldr": "1-2 句",
  "key_points": [
    {"point": "...", "evidence": "来自原文的短句/段落概括", "confidence": 0.0}
  ],
  "ai_pm_takeaways": [
    {"takeaway": "...", "why": "...", "action": "..."}
  ],
  "tags": ["Agents", "Eval", "Product", "Infra", "Startup"],
  "entities": {
    "companies": ["..."],
    "projects": ["..."],
    "papers": [{"title": "...", "url": "..."}],
    "people": ["..."]
  },
  "claims": [
    {"claim": "...", "type": "fact|opinion|forecast", "needs_verification": true}
  ],
  "risk_flags": ["paywall", "no_citations", "marketing_tone", "low_evidence"],
  "reading_time_min": 0,
  "summary_confidence": 0.0
}
```

### 约束
- 输出中文为主，关键名词保留英文
- 不要编造论文/链接；没有就留空
- 如果内容不全，明确写进 risk_flags，并降低 summary_confidence

---

## L1：重要性评分（Score）

### 输入
- L0 summary_json
- title / url
- published_at

### 输出 JSON Schema
```json
{
  "relevance": {
    "agents": 0.0,
    "eval": 0.0,
    "product": 0.0,
    "engineering": 0.0,
    "biz": 0.0
  },
  "novelty": 0.0,
  "actionability": 0.0,
  "credibility": 0.0,
  "overall": 0.0,
  "grade": "A|B|C",
  "rationale": "1-2 句，解释为什么",
  "push_recommended": true
}
```

### 约束
- `overall` 必须是基于 rubric 的加权结果（见 08-ranking-rubric.md）
- `push_recommended`：A 且未达每日上限才 true

---

## L2：核验（Verify）

### 输入
- entry content + L0 + L1
- 可用工具：fetch(url), search(query), extract(page)

### 输出 JSON Schema
```json
{
  "verdict": "verified|partially_verified|uncertain",
  "confidence": 0.0,
  "verified_claims": [
    {"claim": "...", "evidence": [{"url": "...", "snippet": "...", "type": "paper|doc|repo|news"}]}
  ],
  "unverified_claims": [
    {"claim": "...", "reason": "..."}
  ],
  "notes": "面向 AI PM 的解释：哪些可信，哪些不确定，风险是什么",
  "recommended_actions": [
    {"action": "...", "owner": "pm|eng|research", "effort": "S|M|L"}
  ]
}
```

### 约束
- snippet 必须短（<=25 words 的原文引用原则，尽量改写）
- 优先引用：论文/官方文档/GitHub repo/一手来源
- 若无可靠证据：verdict=uncertain，并说明不确定点

---

## Digest：日报生成

### 输入
- window 内 entry 列表（带 L0/L1/L2）
- Top N 限制（比如 30 条）

### 输出 JSON Schema（示例）
```json
{
  "window": {"start": "...", "end": "..."},
  "top_items": [{"entry_id": 1, "title": "...", "why_important": "..."}],
  "clusters": [
    {
      "topic": "Agents",
      "summary": "1-2句",
      "items": [{"entry_id": 1, "title": "..."}]
    }
  ],
  "trend_radar": [{"keyword": "context engineering", "count": 4}],
  "action_recommendations": [
    {"action": "...", "reason": "...", "next_step": "..."}
  ]
}
```

---

## Chat：/ask 回复生成

### 输入
- user_query
- retrieved_chunks（文本 + 引用 entry_id/url）
- retrieved_summaries（摘要）

### 输出 JSON Schema
```json
{
  "answer": "回答（中文为主）",
  "sources": [{"entry_id": 1, "title": "...", "url": "..."}],
  "followups": ["你可以追问的问题1", "问题2"]
}
```
