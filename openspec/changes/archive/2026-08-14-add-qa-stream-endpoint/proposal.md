## Why

`enhance-qa-context-with-intent-and-summary` 落地了意图 agent + 摘要 agent，但前端打字机文案无法反映后端真实阶段：当前 `POST /api/qa/ask` 是单次同步请求，意图分类、检索、回答 LLM 全部黑盒发生在一次 HTTP 往返内。用户反馈期望：

- 意图=RAG 且检索进行中 → 文案「检索中...」
- 检索完成或 chat 意图 → 文案「思考中...」

要满足该 UX，前端必须能感知后端阶段切换。最佳实践是 SSE 流式响应：后端在每个阶段 emit 事件，前端按事件更新打字机文案与气泡。本次新增 `POST /api/qa/ask/stream` SSE 端点（与现有 `POST /api/qa/ask` 并存，向后兼容），后端 `rag.ask` 重构为生成器按阶段 yield 事件，单一逻辑源真相同时供同步与流式端点使用。

## What Changes

### 后端

- **重构** `app/services/rag.py`：新增 `ask_stream_events(db, user, question, session_id, session_title) -> Iterator[tuple[str, dict]]` 生成器，按阶段 yield `(event_name, data)`：
  - `session` — `{session_id, session_title}`（会话解析后立即 emit，便于前端锁定会话）
  - `intent` — `{intent, reason}`
  - `retrieval_started` — `{}`（仅 rag 路径）
  - `retrieval_completed` — `{retrieval_details, citations, top_chunks}`（仅 rag 路径且非早期拒答；早期拒答路径 emit `refused` 后跳过）
  - `answer_started` — `{}`
  - `answer` — `{text, refused, missing_conditions, warning}`（回答 LLM 完成后 emit；拒答路径 emit `answer` 含 `refused=true` 与 missing_conditions）
  - `done` — `{session_id, message_id, session_title, model_info, retrieval_scope, retrieval_details, citations, refused, missing_conditions}`（持久化完成后 emit；前端据此回填 session_id/message_id 与最终结构）
- **改造** `ask(db, user, question, session_id, session_title) -> dict`：薄包装，drain `ask_stream_events` 生成器，取最后 `done` 事件的 data 返回。逻辑零重复。
- **新增端点** `app/api/qa.py::POST /api/qa/ask/stream`：用 `StreamingResponse(media_type="text/event-stream")` 包装 `ask_stream_events`，每个事件格式化为 `event: <name>\ndata: <json>\n\n`。请求体复用 `QAAskIn`。
- **保留** `POST /api/qa/ask`：行为不变，继续供现有测试与非流式客户端使用。

### 前端

- **新增** `frontend/src/api.ts::apiAskQuestionStream(question, sessionId?, sessionTitle?, onEvent)`：用 `fetch` + `ReadableStream` 解析 SSE，按事件回调。失败时抛异常（与 `apiAskQuestion` 一致）。
- **改造** `frontend/src/pages/TrustedQA.tsx::ask`：
  - 新增 `phase: "thinking" | "retrieving"` 状态，打字机文案 = `phase === "retrieving" ? "检索中..." : "思考中..."`。
  - 事件处理：
    - `session` → 锁定 sessionId，刷新会话列表
    - `intent` → `intent==="rag"` 时设 `phase="retrieving"`，否则保持 `thinking`
    - `retrieval_started` → 保持 `retrieving`
    - `retrieval_completed` → 切回 `phase="thinking"`
    - `answer_started` → 保持 `thinking`
    - `answer` → 关闭打字机，开始打字机流式渲染 answer.text
    - `refused` → 关闭打字机，渲染拒答警示
    - `done` → 回填 lastScope 与 session_id/message_id，刷新会话列表
  - 现有打字机流式、引用卡片、检索面板、拒答警示、摘要横幅、会话侧栏全部保留。

### 规格基线

- **MODIFIED** `openspec/specs/decision-qa/spec.md`：
  - 「大模型归纳生成」需求补充：当请求 `Accept: text/event-stream` 或调用 `/api/qa/ask/stream` 时，系统 SHALL 按阶段 emit SSE 事件；事件顺序与字段约束见下。
- **ADDED** `openspec/specs/decision-qa/spec.md`：
  - 「流式问答 SSE」需求：阶段事件顺序、字段约束、降级路径、错误事件格式。

## Capabilities

### Modified Capabilities
- `decision-qa`：从「同步单次响应」升级为「同步 + 流式双端点」，流式端点按阶段反馈意图/检索/回答进度。检索管线、双 agent 架构、会话生命周期全部不变。

## Impact

- 代码：`labmemory-platform/` 内重构 `rag.ask` 为生成器（逻辑零重复），新增 1 个 SSE 端点，前端替换 `apiAskQuestion` 为流式版本并加 `phase` 状态。**不动**：检索管线、意图/摘要/回答三 agent、会话 CRUD、索引器、DB schema。
- API：新增 `POST /api/qa/ask/stream`；现有 `POST /api/qa/ask` 行为不变（向后兼容，测试不动）。
- 数据：无 schema 变更，无迁移。
- 依赖：**无新增依赖**，复用 FastAPI `StreamingResponse` 与浏览器原生 `ReadableStream`。
- 性能：流式端点不再让客户端等待完整响应才显示进度；意图事件 ~1s 后到达，检索事件 ~100ms 后到达，回答事件在 LLM 完成后到达。chat 路径无检索事件，直接进入 `answer_started`。
- 保密：SSE 事件数据仍是脱敏的 Claim/Result/Evidence 文本片段与检索元数据，不含妙记原文或 Token。
