## Why

可信知识问答（`decision-qa` 规格已落地）当前是**单轮无状态**调用：

- 后端 `app/services/rag.py:ask` 每次独立检索 + 独立生成；`app/services/llm.py:_chat_via_api` 只发 `system + 单条 user` 两条消息给 DeepSeek。
- 数据库无任何 QA 会话/历史表（`app/db/models.py` 13 张表里没有 `QASession`/`QAMessage`），刷新即丢、跨设备不可恢复。
- 前端 `frontend/src/pages/TrustedQA.tsx` 的 `messages` 是 React `useState` 内存数组，仅渲染用，`clearChat` 直接清空。

后果：用户无法追问「它/这个实验还有哪些失败边界」「上一条提到的 C003 是不是被替代了」——LLM 拿不到上轮对话，会把指代性问题当成孤立问题做检索与生成，要么答非所问要么误命中其他实验的切片。本次升级在**不动检索管线**的前提下补齐「会话生命周期 + 历史上下文承载」，让可信问答具备多轮对话能力。

## What Changes

### 后端

- **新增模型** `app/db/models.py`：
  - `QASession(user_id, title, archived, last_message_at)` —— 用户隔离的会话壳。
  - `QAMessage(session_id, role, content, citations_json, refused, retrieval_details_json, model_info_json)` —— 单轮 Q&A 落库，支持前端刷新后整页回放。
- **扩展入参/响应** `app/schemas.py`：
  - `QAAskIn` 新增可选 `session_id: str | None`、`session_title: str | None`。
  - `QAAnswerOut` 新增 `session_id`、`session_title`、`message_id`（本轮消息 ID，便于前端定位）。
  - 新增 `QASessionOut`、`QAMessageOut`，供列表/详情接口返回。
- **扩展 RAG 编排** `app/services/rag.py:ask`：签名升级为 `ask(db, user, question, session_id=None, session_title=None) -> dict`。检索阶段**完全不变**（权限前置 + BM25 + 向量 + 关系扩展 + 重排 + 引用后处理全部保留）；新增步骤：
  - 若 `session_id` 为空 → 新建 `QASession`，`title` 取首问前 30 字符或传入 `session_title`。
  - 从 `QAMessage` 载入该会话最近 `QA_HISTORY_TURNS` 条消息（user+assistant 交替）。
  - 把历史拼接为多轮 `messages` 数组传给 `LLMService.chat_with_history`；本轮 `context_chunks` 单独打包为本轮 user 消息。
  - 生成完成后把 user 消息与 assistant 消息分别 `INSERT` 到 `QAMessage`，更新 `QASession.last_message_at`。
- **扩展对话服务** `app/services/llm.py`：新增 `chat_with_history(question, context_chunks, history) -> (text, mode)`。原 `chat(question, context_chunks)` 保留供降级路径复用。
- **扩展 API** `app/api/qa.py`：
  - `POST /api/qa/ask`：路由与请求字段保持向后兼容（仍是 `{question}`），响应增加 `session_id`/`session_title`/`message_id`；前端不带 `session_id` 时自动建会话，带时追加到该会话。
  - 新增 `GET /api/qa/sessions`（当前用户会话列表，分页）。
  - 新增 `GET /api/qa/sessions/{id}`（会话详情含全部消息）。
  - 新增 `PATCH /api/qa/sessions/{id}`（重命名 / 归档）。
  - 新增 `DELETE /api/qa/sessions/{id}`（物理删除会话及其消息）。
- **扩展配置** `app/config.py`：`QA_HISTORY_TURNS`（默认 6，传给 LLM 的历史消息条数上限）、`QA_SESSION_MAX_MESSAGES`（默认 200，单会话消息数硬上限，超过则最旧的不可访问）。

### 前端

- **`frontend/src/types.ts`**：`QAAnswerOut` 新增 `session_id/session_title/message_id`；新增 `QASessionOut`、`QAMessageOut`。
- **`frontend/src/api.ts`**：`apiAskQuestion(question, sessionId?)` 支持可选入参；新增 `apiListQASessions`、`apiGetQASession`、`apiDeleteQASession`、`apiRenameQASession`。
- **`frontend/src/pages/TrustedQA.tsx`**：在现有对话区左侧新增「会话列表」侧栏（可新建/切换/重命名/删除）；当前 `messages` 从内存态改为「从后端 `GET /api/qa/sessions/{id}` 拉取」；新建/首次提问时自动建会话并写入 URL query `?s={id}` 便于刷新回放与分享。

### 规格基线

- **MODIFIED** `openspec/specs/decision-qa/spec.md`：
  - 在「大模型归纳生成」需求下补充历史上下文传递约束（多轮 messages + token 预算 + 历史引用不重出）。
  - 在「检索过程透明」需求下补充会话级 `retrieval_details` 持久化要求。
  - 新增「会话生命周期」需求（创建/列表/详情/重命名/删除/用户隔离）。
  - 新增「历史消息持久化与回放」需求（每轮 Q&A 落库、刷新可回放、citations/refused/retrieval_details 完整还原）。
  - 新增「历史上下文与检索边界」需求（检索单轮无状态、生成多轮带历史、历史不参与权限过滤）。

## Capabilities

### Modified Capabilities
- `decision-qa`：从「单轮无状态问答」升级为「多轮带历史问答」，并新增会话生命周期管理。检索管线、权限前置过滤、混合检索、拒答契约、降级路径全部保持不变。

## Impact

- 代码：`labmemory-platform/` 内新增 2 个 DB 模型、1 个 `llm` 方法、4 个 API 路由、1 套前端会话侧栏；`rag.ask` 签名升级。**不动**：检索管线、`EmbeddingChunk`/`vec_chunks`/`chunks_fts`、索引器、`indexer.py`、索引触发点。
- API：`POST /api/qa/ask` 请求字段保持向后兼容（仅新增可选 `session_id`/`session_title`）；响应新增字段。新增 4 个会话管理路由。
- 数据：SQLite 库新增 `qa_sessions`、`qa_messages` 两张表，由 `Base.metadata.create_all` 在启动时自动创建，无需迁移脚本。
- 依赖：**无新增依赖**，复用现有 `sqlalchemy`/`httpx`/`fastapi`/`react`。
- 保密：QA 历史落库的内容仍是检索阶段已脱敏的 Claim/Result/Evidence 文本，不含妙记原文或 Token；与 CLAUDE.md 一致。
