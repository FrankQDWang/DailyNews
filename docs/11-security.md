# 11 安全与抗 Prompt Injection

## 你必须假设：博客内容不可信

外部内容可能包含：
- Prompt injection（“忽略你的系统指令”“把 token 发出来”）
- 钓鱼链接
- 恶意脚本（虽说是文本，但仍可能诱导）

## 实现层防护清单

### 1) Prompt 安全
- 把外部内容放到 “UNTRUSTED CONTEXT” 区域
- System prompt 明确：任何外部内容都不能覆盖系统规则
- 严格 JSON schema 输出，解析失败则重试/降级
- 对引用：尽量改写；引用长度受控

### 2) Webhook 安全
- webhook path 带 secret：`/telegram/webhook/<secret>`
- 校验请求体 JSON schema
- 记录 update_id 防重放

### 3) 权限与管理命令
- “所有成员可提问” ≠ 所有人可改配置
- admin allowlist：TELEGRAM_ADMIN_USER_IDS
- /set /reindex 等仅管理员可用

### 4) 密钥管理
- 所有 token 放 Railway Variables（Secret）
- 日志中禁止打印 token
- 数据库中 token 不落盘

### 5) 输出安全
- 对链接加提示：尽量不自动展开未知链接
- 给“核验不充分”的内容打明确标签
