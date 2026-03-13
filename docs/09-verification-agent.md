# 09 A 级核验 Agent 设计（L2）

目标：用可控成本把“A 级推送”的可信度显著提高。

## 触发
- grade == A → 自动核验
- 或 `/deepdive <id>` 手动触发（对 B/C 也可以）

---

## 核验策略（MVP 到增强）

### MVP（必须）
1) 从 L0.claims 中挑选 3–7 条最关键（优先：数字、SOTA、性能提升、成本下降、可复现）
2) 解析文章中显式链接（论文、repo、官方文档）
3) 对每条 claim：
   - 若有引用链接：fetch 链接页面，提取 title/abstract/关键句（不要长引用）
   - 若无引用链接：用 search 工具找 1–3 个高质量来源验证（paper/doc/repo/公告）

输出：
- verdict + confidence
- verified_claims / unverified_claims
- evidence 列表
- 对 AI PM 的解释 + 可执行建议

### 增强（可选）
- 发现同一话题的反对观点（找“counter evidence”）
- 对 benchmark/评测：检查评测设置、对比基线、是否 cherry-pick
- 对开源 repo：检查最近 commits、stars、issues（粗略判断成熟度）
- 对产品/商业：识别营销话术与缺失数据，给风险提示

---

## 工具接口（建议抽象层，便于换 provider）

- `fetch(url) -> {status, final_url, title, text, html}`
- `search(query, top_k=5, domains_allowlist=None) -> [{url,title,snippet}]`
- `extract_claims(text) -> [claim]`（可用 LLM）
- `quote_guard(text) -> snippet`（保证引用短、避免版权问题）

注意：
- 对外部网页抓取要有 timeout、重试、robots 风险提示
- evidence 优先“第一手来源”：论文、官方文档、GitHub repo、项目公告

---

## 输出渲染到 Telegram（建议）

对 A 级快讯，核验后追加一段：

核验：partially_verified（0.74）
- ✅ 主张1：...（证据：repo/paper）
- ⚠️ 主张2：未找到可靠证据（原因：...）
风险：...
建议：...
