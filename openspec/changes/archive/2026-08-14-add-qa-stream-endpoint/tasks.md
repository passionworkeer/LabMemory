## 1. 后端生成器重构

- [ ] 1.1 `app/services/rag.py`：新增 `ask_stream_events(db, user, question, session_id, session_title) -> Iterator[tuple[str, dict]]` 生成器，按阶段 yield `(event_name, data)`：
  - `session` → `{session_id, session_title}`
  - `intent` → `{intent, reason}`
  - rag 路径：`retrieval_started` → `{}`；正常 → `retrieval_completed` → `{retrieval_details, citations, top_chunks}`；早期拒答 → `refused` → `{reason, missing_conditions, retrieval_details}`
  - `answer_started` → `{}`
  - `answer` → `{text, refused, missing_conditions, warning}`
  - `done` → 完整 `QAAnswerOut` dict（含 session_id/message_id/session_title/model_info/retrieval_scope/retrieval_details/citations/refused/missing_conditions）
- [ ] 1.2 `app/services/rag.py`：`ask(db, user, question, session_id, session_title) -> dict` 改为薄包装，drain `ask_stream_events`，取最后 `done` 事件 data 返回；逻辑零重复。
- [ ] 1.3 保留 `_finalize`/`_resolve_session`/`_load_history`/`_load_recent_history`/`_maybe_summarize` 等辅助函数；生成器内部调用顺序与原 `ask` 一致（resolve → intent → load history → 可选检索 → answer → persist → maybe_summarize）。

## 2. SSE 端点

- [ ] 2.1 `app/api/qa.py`：新增 `POST /api/qa/ask/stream`，请求体复用 `QAAskIn`；用 `fastapi.responses.StreamingResponse(media_type="text/event-stream")` 包装 `rag.ask_stream_events`，每个事件格式化为 `event: <name>\ndata: <json>\n\n`（`json.dumps(ensure_ascii=False)`）。
- [ ] 2.2 SSE 响应头加 `Cache-Control: no-cache`、`X-Accel-Buffering: no`（防代理缓冲）。
- [ ] 2.3 保留 `POST /api/qa/ask`（同步端点）行为不变。

## 3. 前端流式 + phase

- [ ] 3.1 `frontend/src/api.ts`：新增 `apiAskQuestionStream(question, sessionId?, sessionTitle?, onEvent)`，用 `fetch` + `response.body.getReader()` + `TextDecoder` 解析 SSE；按 `event:` / `data:` 行切分，回调 `onEvent(name, data)`；HTTP 非 2xx 时抛 `Error`。
- [ ] 3.2 `frontend/src/pages/TrustedQA.tsx`：
  - 新增 `phase: "thinking" | "retrieving"` 状态；打字机文案 = `phase === "retrieving" ? "检索中..." : "思考中..."`。
  - `ask()` 改用 `apiAskQuestionStream`，按事件回调更新：
    - `session` → 锁定 sessionId（若变更则刷新 URL `?s=`）与 session_title
    - `intent` → `intent==="rag"` 时 `setPhase("retrieving")`，否则保持 `thinking`
    - `retrieval_started` → 保持 `retrieving`
    - `retrieval_completed` → `setPhase("thinking")`
    - `answer_started` → 保持 `thinking`
    - `answer` → 关闭打字机，开始打字机流式渲染 `data.text`；记录 `refused`/`missing_conditions`/`warning`
    - `refused` → 关闭打字机，准备拒答警示渲染
    - `done` → 回填 `lastScope`（构造 `QAAnswerOut`）、`session_id`/`message_id`，刷新会话列表
  - 保留打字机流式、引用卡片、检索面板、拒答警示、摘要横幅、会话侧栏。

## 4. 验证

- [ ] 4.1 `openspec validate add-qa-stream-endpoint` 通过。
- [ ] 4.2 后端 import 自检：`python -c "from app.main import app"`。
- [ ] 4.3 端到端探针：
  - `POST /api/qa/ask/stream` rag 路径：收到 7 个事件（session→intent(rag)→retrieval_started→retrieval_completed→answer_started→answer→done），`done.data.session_id` 与 `session.data.session_id` 一致。
  - chat 路径：收到 5 个事件（无 retrieval_*）。
  - 检索拒答路径：收到 5 个事件（refused 替代 retrieval_completed/answer_started/answer）。
- [ ] 4.4 `pytest tests/` 全量通过（同步端点 /api/qa/ask 行为不变）。
- [ ] 4.5 前端 `npx tsc --noEmit` 通过；`npm run build` 通过。
- [ ] 4.6 `openspec archive add-qa-stream-endpoint --yes` 归档。
