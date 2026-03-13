# 05 数据模型（assistant-db，pgvector Postgres）

## 设计目标

- 存储“条目 + 摘要 + 打分 + 核验证据 + 向量索引 + 对话状态 + 反馈”
- 支持：
  - 去重：同一 URL / 同一 Miniflux entry 不重复
  - 查询：按时间/主题/评分
  - RAG：chunk-level embedding 检索
  - 报表：daily digest 生成与回溯

---

## 核心表（建议）

### 1) sources（可选）
如果你要对 92 源做单独管理（比如暂停某源/权重调整）：
- id
- feed_url
- site_url
- title
- enabled
- default_weight

### 2) entries（从 Miniflux 来）
- id (bigserial)
- miniflux_entry_id (bigint, unique)
- miniflux_feed_id (bigint)
- url (text, unique)  # 需要 canonicalize（去 tracking params）
- title (text)
- author (text)
- published_at (timestamptz)
- fetched_at (timestamptz)
- content_html (text)
- content_text (text)
- content_hash (text) # 便于检测更新
- lang (text)
- status (enum: new|summarized|scored|verified|failed)
- created_at / updated_at

Indexes:
- (published_at desc)
- (status)
- (miniflux_feed_id, published_at)

### 3) entry_chunks（RAG 用）
- id
- entry_id (fk)
- chunk_index (int)
- chunk_text (text)
- token_count (int)
- embedding (vector(N))  # pgvector
- created_at

Indexes:
- (entry_id, chunk_index)
- ivfflat/hnsw index on embedding (按 pgvector 支持的方式)

### 4) summaries（L0）
- id
- entry_id (fk, unique)
- tldr (text)
- key_points (jsonb)
- ai_pm_takeaways (jsonb)
- tags (text[])
- entities (jsonb)  # companies/projects/papers
- risk_flags (text[])
- action_items (jsonb)
- summary_json (jsonb) # 原始结构化输出
- model (text)
- created_at

### 5) scores（L1）
- id
- entry_id (fk, unique)
- relevance_agents (float)
- relevance_eval (float)
- relevance_product (float)
- relevance_engineering (float)
- relevance_biz (float)
- novelty (float)
- actionability (float)
- credibility (float)
- overall (float)
- grade (enum: A|B|C)
- rationale (text)
- model (text)
- created_at

### 6) verifications（L2，仅 A）
- id
- entry_id (fk, unique)
- verdict (enum: verified|partially_verified|uncertain)
- verified_claims (jsonb)
- unverified_claims (jsonb)
- evidence (jsonb)  # list of {url, snippet, type, confidence}
- notes (text)
- confidence (float)
- model (text)
- created_at

### 7) push_events（Telegram 推送审计/幂等）
- id
- entry_id (fk, nullable)  # digest 推送可为空
- type (enum: alert|digest|reply)
- telegram_chat_id (bigint)
- telegram_message_id (bigint, nullable)
- payload (jsonb)
- status (enum: sent|failed)
- error (text)
- created_at

Unique/Idempotency:
- (type, entry_id, telegram_chat_id) unique where type='alert'  # 防重复

### 8) daily_reports
- id
- window_start (timestamptz)
- window_end (timestamptz)
- report_markdown (text)
- report_json (jsonb)
- sent_at (timestamptz)
- created_at

### 9) chat_sessions（对话）
- id
- telegram_chat_id
- telegram_user_id
- last_seen_at
- context_json (jsonb)   # 轻量记忆（可选）
- created_at / updated_at

### 10) user_feedback（反馈闭环）
- id
- entry_id
- telegram_chat_id
- telegram_user_id
- feedback (enum: up|down|save|mute_source)
- note (text)
- created_at

---

## 数据保留策略（建议）

- content_html/content_text：保留 90 天（可配置）
- chunks + embeddings：保留 180 天（可配置）
- summaries/scores/verifications：长期保留（核心资产）
- 原文链接永不删
