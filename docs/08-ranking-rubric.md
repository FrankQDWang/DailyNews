# 08 重要性分级 Rubric（为你的角色定制）

## 评分维度（0~1）

- relevance_agents
- relevance_eval
- relevance_product
- relevance_engineering
- relevance_biz
- novelty（新不新/是否超出常识）
- actionability（能否转为行动）
- credibility（证据质量/引用/实验/可复现）

## 权重（建议，可调）

你的关注点是：
Agents / Eval / 产品策略 / 工程化落地 / 创业商业化

因此建议权重：

- relevance_agents: 0.22
- relevance_eval: 0.18
- relevance_product: 0.18
- relevance_engineering: 0.16
- relevance_biz: 0.12
- novelty: 0.08
- actionability: 0.04
- credibility: 0.02  （注意：credibility 不是不重要，而是会在“是否推送/是否核验”上额外 gate）

> 解释：你每天读的东西里，“相关性”比“泛新颖”更重要；credibility 单独作为 gate（低可信直接不推 A）。

## overall 计算

```
overall = Σ(weight_i * score_i)
```

## Grade 划分（建议）

- A：overall >= 0.78 且 credibility >= 0.55 且 summary_confidence >= 0.60
- B：0.55 <= overall < 0.78
- C：overall < 0.55

## 推送 gate（是否发 A 级快讯）

同时满足：
1) grade == A
2) 今日 A 级未达 10 条
3) 通过 L2（verdict != uncertain）  
   - 如果 verdict=uncertain，但仍特别重要：允许以 “A- 未完全核验” 推送（可配置），并显式标注风险

---

## 反馈闭环（建议加分/降权）

如果用户对某条做了 👍：
- 同源/同主题未来 7 天加权 +0.03（最多 +0.10）

如果 👎：
- 同源未来 7 天加权 -0.05（最多 -0.20）
- 或降低其 default_weight

如果 “mute source”：
- sources.enabled=false（直接暂停）
