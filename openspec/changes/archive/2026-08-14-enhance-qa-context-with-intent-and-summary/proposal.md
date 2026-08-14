## Why

`add-qa-session-history` 已落地多轮历史持久化，但上下文管理仍存在三个工程问题：

1. **历史窗口硬截断、超限即丢**：`_load_history` 只取最近 `QA_HISTORY_TURNS`（默认 6）条消息，更早消息既不进 LLM 也不进任何压缩。用户长会话里第 7 轮之前讨论过的实验编号、参数版本、已确立指代在 LLM 视角里"凭空消失"，导致追问时 LLM 重新出现"它指的是什么"的歧义回答——这就是用户反馈的"上下文丢失"根因。
2. **每轮必检索**：寒暄、致谢、指代消解型追问（"刚才那个再展开说说"）也被强行跑一遍 RAG 检索，浪费延迟与 token；更糟的是这类追问检索到的切片常常与本轮意图无关，污染回答。
3. **意图与上下文不可见**：无法回看"这一轮是否检索过、被压缩了多少轮"，调试与回放都缺信息。

本次升级引入双 agent 架构（意图识别 agent + 摘要压缩 agent）+ 滚动摘要持久化，使上下文窗口结构稳定可控：`[system → 历史摘要 → 近 N 轮完整对话 → 本轮(可选检索结果)]`。

## What Changes

### 后端

- **新增模型字段** `app/db/models.py`：
  - `QASession.summary: Text | None` —— 滚动摘要正文。
  - `QASession.summary_cursor: int | None` —— 已折叠进 summary 的最大 message_id（幂等游标，避免重复压缩）。
  - `QAMessage.intent: str | None` —— 仅 user 消息记录 `rag` / `chat`，便于回放与统计。
- **扩展配置** `app/config.py`：
  - `QA_HISTORY_TURNS` 默认改为 10（语义：保留近 10 轮完整对话 = 20 条消息）。
  - `QA_ENABLE_INTENT`（默认 true）—— 意图 agent 总开关；false 时所有问题都走 RAG（向后兼容降级）。
  - `QA_INTENT_MODEL`（默认沿用 `DEEPSEEK_CHAT_MODEL`）—— 意图 agent 可单独配模型。
  - `QA_SUMMARY_MAX_CHARS`（默认 600）—— 摘要正文硬上限。
- **新增意图 agent** `app/services/llm.py::classify_intent(question, recent_history) -> ("rag"|"chat", reason)`：独立 system prompt，要求严格 JSON 输出 `{"intent":"rag|chat","reason":"..."}`；解析失败或 LLM 不可用 → 默认 `("rag", "fallback")`（宁检索勿漏）。
- **新增摘要 agent** `app/services/llm.py::summarize_history(existing_summary, old_messages) -> str`：独立 system prompt，要求中文 ≤300 字，保留实验编号/参数/知识状态/失败边界/已确立指代；增量更新已有摘要；LLM 不可用 → 返回空串（调用方据此跳过压缩，保留旧消息原样）。
- **改造回答 agent 调用** `app/services/llm.py::chat_with_history`：messages 组装升级为 `[system] + [可选摘要 system 消息] + 历史消息对 + [本轮 user(含 <context> 与 <question>，或仅 <question>)]`。
- **改造 RAG 编排** `app/services/rag.py::ask`：
  1. 解析会话（不变）。
  2. **意图分类**：调 `classify_intent(question, recent_history_window)`；`intent == "chat"` 且 `QA_ENABLE_INTENT=true` 时**跳过检索**，`context_chunks=[]`，`retrieval_details={"skipped_by_intent": true, ...}`；`intent == "rag"` 时走原检索管线（权限/状态/BM25/向量/关系扩展/重排全部保留）。
  3. **加载上下文窗口**：`summary = session.summary`；`history = 最近 QA_HISTORY_TURNS 轮完整消息`（按轮数 × 2 取消息数）。
  4. **回答生成**：`llm.chat_with_history(question, context_chunks, history, summary)`。
  5. **持久化**：user 消息记录 `intent`；assistant 消息照旧。
  6. **滚动压缩**：调 `_maybe_summarize(db, session)`——若未折叠消息数 > `QA_HISTORY_TURNS*2 + 2`，把最旧的超出部分（按对齐到 user/assistant pair）经 `summarize_history` 折叠进 `session.summary`，推进 `summary_cursor`。
- **扩展 schema** `app/schemas.py`：`QASessionDetailOut` 加 `summary`/`summary_cursor`；`QAMessageOut` 加 `intent`。

### 前端

- **`frontend/src/types.ts`**：`QASessionDetailOut` 加 `summary?/summary_cursor?`；`QAMessageOut` 加 `intent?`。
- **`frontend/src/pages/TrustedQA.tsx`**：
  - 会话切换拉取详情时，若 `summary` 非空，在消息列表顶部渲染摘要横幅（"已折叠 N 轮早期对话" + 折叠展开）。
  - user 消息气泡底部展示意图小标签（🔍检索 / 💬对话），便于回看哪几轮做过 RAG。

### 规格基线

- **MODIFIED** `openspec/specs/decision-qa/spec.md`：
  - 「大模型归纳生成」需求补充：回答 agent 上下文结构 = `[system → 摘要 → 近 N 轮 → 本轮]`；当 `intent=chat` 时本轮不含 `<context>`。
  - 「历史消息持久化与回放」需求补充：`QAMessage.intent` 与 `QASession.summary/summary_cursor` 字段约束；刷新回放时若 `summary` 非空 SHALL 渲染摘要横幅。
- **ADDED** `openspec/specs/decision-qa/spec.md`：
  - 「意图识别 agent」需求：分类输出格式、降级路径、chat 跳过检索、宁检索勿漏。
  - 「历史滚动摘要」需求：触发条件、折叠对齐到 pair、`summary_cursor` 幂等、摘要内容要求、LLM 不可用跳过。

## Capabilities

### Modified Capabilities
- `decision-qa`：从「单 agent 单轮历史」升级为「意图 agent + 摘要 agent + 回答 agent」三角色协作的滚动窗口上下文管理；检索管线零改动。

## Impact

- 代码：`labmemory-platform/` 内新增 2 个模型字段、2 个 LLM 方法、1 套滚动压缩逻辑；`rag.ask` 流程升级。**不动**：检索管线、`EmbeddingChunk`/`vec_chunks`/`chunks_fts`、索引器、索引触发点、会话 CRUD 路由签名。
- API：`POST /api/qa/ask` 入参/响应字段保持兼容（无新增字段）；`GET /api/qa/sessions/{id}` 响应新增 `summary/summary_cursor/intent` 三个只读字段。
- 数据：SQLite 库 `qa_sessions` 表 `ALTER TABLE ADD COLUMN summary TEXT, summary_cursor INTEGER`；`qa_messages` 表 `ALTER TABLE ADD COLUMN intent VARCHAR(16)`。由 `_run_migrations` 幂等执行，已存数据不受影响。
- 依赖：**无新增依赖**，复用现有 `httpx`/`sqlalchemy`/`fastapi`。
- 性能：意图 agent 增加 1 次 LLM 调用（chat 类问题节省 1 次完整 RAG，净延迟更低）；摘要 agent 仅在超窗口时触发，平均每 N 轮 1 次。
- 保密：摘要正文仍是已脱敏的 Claim/Result/Evidence 文本片段；与 CLAUDE.md 一致。
