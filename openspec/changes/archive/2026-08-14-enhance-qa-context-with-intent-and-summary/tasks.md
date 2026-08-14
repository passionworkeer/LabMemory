## 1. 数据模型与配置

- [ ] 1.1 `app/db/models.py`：`QASession` 加 `summary: Text | None`、`summary_cursor: Integer | None`（索引）；`QAMessage` 加 `intent: str | None`（仅 user 消息记录）。
- [ ] 1.2 `app/main.py::_run_migrations`：幂等 `ALTER TABLE qa_sessions ADD COLUMN summary TEXT`、`ADD COLUMN summary_cursor INTEGER`；`ALTER TABLE qa_messages ADD COLUMN intent VARCHAR(16)`（检测列存在再 ADD，与 tasks 表迁移风格一致）。
- [ ] 1.3 `app/config.py`：`QA_HISTORY_TURNS` 默认改 10；新增 `QA_ENABLE_LLM_INTENT`（默认 true）、`QA_INTENT_MODEL`（默认 `DEEPSEEK_CHAT_MODEL`）、`QA_SUMMARY_MAX_CHARS`（默认 600）。
- [ ] 1.4 `.env.example` 同步。

## 2. Schema

- [ ] 2.1 `app/schemas.py`：`QAMessageOut` 加 `intent: str | None`；`QASessionDetailOut` 加 `summary: str | None`、`summary_cursor: int | None`。

## 3. 双 agent 实现

- [ ] 3.1 `app/services/llm.py`：新增 `INTENT_SYSTEM_PROMPT`（强制 JSON 输出、宁检索勿漏）。
- [ ] 3.2 `app/services/llm.py`：`classify_intent(question, recent_history) -> ("rag"|"chat", reason)`；独立 httpx 调用，`temperature=0`；JSON 解析失败/异常 → `("rag", "fallback")`；`QA_ENABLE_LLM_INTENT=false` 或 LLM 不可用 → `("rag", "fallback")`。
- [ ] 3.3 `app/services/llm.py`：新增 `SUMMARY_SYSTEM_PROMPT`（≤300 字、保留实验编号/参数/知识状态/失败边界/指代/偏好）。
- [ ] 3.4 `app/services/llm.py`：`summarize_history(existing_summary, old_messages) -> str`；LLM 不可用或异常 → 返回空串（调用方据此跳过推进 cursor）；输出截断到 `QA_SUMMARY_MAX_CHARS` 由调用方执行。
- [ ] 3.5 `app/services/llm.py`：扩展 `chat_with_history(question, context_chunks, history, summary=None)`：messages 组装顺序 = system → 可选摘要 system → 历史 pair → 本轮 user（context_chunks 非空时含 `<context>`+`<question>`，否则仅 `<question>`）。

## 4. RAG 编排改造

- [ ] 4.1 `app/services/rag.py::ask`：
  - 解析会话（不变）。
  - 调 `classify_intent(question, _load_recent_history(db, session, 4))`。
  - `intent == "chat"` 且 `QA_ENABLE_LLM_INTENT`：跳过检索管线，`context_chunks=[]`，`retrieval_details={"skipped_by_intent": True, "intent": "chat", "intent_reason": reason, "permission_filtered_experiments": len(_user_experiments(db, user))}`。
  - `intent == "rag"`：走原检索管线（权限/状态/BM25/向量/关系扩展/重排全部保留），`retrieval_details.skipped_by_intent=False`、`retrieval_details.intent_reason=reason`。
- [ ] 4.2 上下文窗口加载：`summary = session.summary`；`history = _load_history(db, session)`（最近 QA_HISTORY_TURNS 轮 = 2N 条消息）。
- [ ] 4.3 回答 agent 调用：`llm.chat_with_history(question, context_chunks, history, summary)`；拒答路径同样经过此调用。
- [ ] 4.4 引用后处理：`intent=chat` 时 `citations=[]`、`extract_citation_refs` 不调用（避免误把历史 `[Cx]` 当本轮引用）。
- [ ] 4.5 持久化：user 消息 `intent=intent`；assistant 消息照旧；调 `_maybe_summarize(db, session)`。
- [ ] 4.6 新增 `_maybe_summarize(db, session)`：计算 `fresh_keep = QA_HISTORY_TURNS*2`；若 `total_messages > fresh_keep + 2` 且 `oldest_fresh_id > summary_cursor`，取折叠区间 pair 消息，调 `summarize_history`，非空则更新 `session.summary/summary_cursor`，commit；空则不推进。
- [ ] 4.7 新增 `_load_recent_history(db, session, n) -> list[dict]`：取最近 n 条消息（不分角色），供意图 agent 轻量使用。

## 5. API

- [ ] 5.1 `app/api/qa.py::get_session`：响应 `messages` 里 user 消息透传 `intent`；会话级透传 `summary`/`summary_cursor`。

## 6. 前端

- [ ] 6.1 `frontend/src/types.ts`：`QAMessageOut` 加 `intent?: string | null`；`QASessionDetailOut` 加 `summary?: string | null`、`summary_cursor?: number | null`。
- [ ] 6.2 `frontend/src/pages/TrustedQA.tsx`：
  - `loadSession` 后存储 `summary`/`summary_cursor` 到 state。
  - 消息列表顶部渲染摘要横幅（`summary` 非空时）：折叠展开按钮 + "已折叠到第 X 条消息" + 摘要正文。
  - user 消息气泡底部小标签：`intent==="rag"` → "🔍 检索"，`intent==="chat"` → "💬 对话"。
  - `messageToMsg` 透传 `intent` 字段到 `Msg`。

## 7. 验证

- [ ] 7.1 `openspec validate enhance-qa-context-with-intent-and-summary` 通过。
- [ ] 7.2 后端 import 自检：`python -c "from app.main import app"`。
- [ ] 7.3 端到端探针：
  - 提问「EXP-DEMO-001 推荐温度」→ intent=rag，citations 非空，session_id 返回。
  - 在同会话追问「谢谢你」→ intent=chat，`retrieval_details.skipped_by_intent=true`，citations 为空，user 消息 intent=chat 落库。
  - 追问「把刚才那段用一句话复述」→ intent=chat，回答中无新 `[Cx]`。
  - 跑 12+ 轮对话 → `session.summary` 非空，`summary_cursor > 0`，GET session 详情能看到 summary。
- [ ] 7.4 跨用户访问会话仍 403；删除会话级联清消息+summary。
- [ ] 7.5 `pytest tests/` 全量通过（含 `test_qa_degrades_without_vector_not_503` 回归）。
- [ ] 7.6 前端 `npx tsc --noEmit` 通过；`npm run build` 通过。
- [ ] 7.7 `openspec archive enhance-qa-context-with-intent-and-summary --yes` 归档。
