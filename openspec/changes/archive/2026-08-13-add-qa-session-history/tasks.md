## 1. 数据模型与配置

- [ ] 1.1 `app/db/models.py`：新增 `QASession(user_id, title, archived, last_message_at)` 与 `QAMessage(session_id, role, content, citations_json, refused, retrieval_details_json, model_info_json, missing_conditions_json)`；继承 `Base + IDMixin + TimestampMixin`；`QAMessage.session_id` 外键 `ON DELETE CASCADE`；`QASession.user_id` 外键 + 索引。
- [ ] 1.2 `app/config.py`：新增 `QA_HISTORY_TURNS`（默认 6）、`QA_SESSION_MAX_MESSAGES`（默认 200）、`QA_SESSION_LIST_DEFAULT_LIMIT`（默认 20）；`.env.example` 同步。
- [ ] 1.3 自检：`Base.metadata.create_all` 在启动时自动建 `qa_sessions`/`qa_messages` 两表（无需 migration）。

## 2. Schema

- [ ] 2.1 `app/schemas.py`：`QAAskIn` 新增可选 `session_id: str | None`、`session_title: str | None`；`QAAnswerOut` 新增 `session_id: str | None`、`session_title: str | None`、`message_id: int | None`。
- [ ] 2.2 `app/schemas.py`：新增 `QASessionOut`（id/title/archived/last_message_at/message_count/created_at）、`QAMessageOut`（id/role/content/citations/refused/retrieval_details/model_info/missing_conditions/created_at）、`QASessionDetailOut`（session + messages[]）、`QASessionPatchIn`（title?/archived?）。

## 3. LLM 多轮生成

- [ ] 3.1 `app/services/llm.py`：`SYSTEM_PROMPT` 末尾追加历史消解规则（指代消解 + history 不足时 REFUSED）。
- [ ] 3.2 `app/services/llm.py`：新增 `chat_with_history(question, context_chunks, history) -> (text, mode)`；`history` 单条文本超 2000 字符截断追加 `[已截断]`；messages 组装为 `system + history_pairs + 本轮 user(含 <context>+<question>)`；DeepSeek 不可用或异常时降级到 `_template_answer`（不参考 history）。
- [ ] 3.3 `chat()` 原签名保留（兼容路径/测试）。

## 4. RAG 编排升级

- [ ] 4.1 `app/services/rag.py`：`ask(db, user, question, session_id=None, session_title=None) -> dict`；检索阶段（步骤 1-7）**完全不动**。
- [ ] 4.2 会话解析：`session_id is None` → 新建 `QASession(title=session_title or question[:30])`；非空 → 校验 `user_id` 匹配 + 未归档，否则抛 `PermissionDeniedError`/`NotFoundError`。
- [ ] 4.3 历史载入：取该 session 最近 `QA_HISTORY_TURNS` 条 `QAMessage`（按 `id DESC` 取后逆序），转为 `[{role, content}, ...]`。
- [ ] 4.4 LLM 调用：把原 `llm.chat(question, context_chunks)` 替换为 `llm.chat_with_history(question, context_chunks, history)`；拒答路径同样经过此调用。
- [ ] 4.5 持久化：在返回前 `INSERT` 两条 `QAMessage`（user + assistant，assistant 携带 `citations_json`/`refused`/`retrieval_details_json`/`model_info_json`/`missing_conditions_json`）；`UPDATE QASession.last_message_at`；返回 dict 新增 `session_id`/`session_title`/`message_id`。
- [ ] 4.6 拒答路径也持久化（与正常路径同样落库两条消息）。

## 5. API 路由

- [ ] 5.1 `app/api/qa.py`：`POST /api/qa/ask` 入参升级为 `QAAskIn`（含可选 session_id/title），响应直接透传 `rag.ask` 返回的 `session_id`/`session_title`/`message_id`。
- [ ] 5.2 `app/api/qa.py`：新增 `GET /api/qa/sessions?limit=&offset=&include_archived=`，按 `(user_id, archived, last_message_at DESC)` 过滤分页，返回 `list[QASessionOut]`。
- [ ] 5.3 `app/api/qa.py`：新增 `GET /api/qa/sessions/{id}`，校验 owner，返回 `QASessionDetailOut`（messages 按 `QA_SESSION_MAX_MESSAGES` 取最近 N 条）。
- [ ] 5.4 `app/api/qa.py`：新增 `PATCH /api/qa/sessions/{id}`，校验 owner，更新 title/archived。
- [ ] 5.5 `app/api/qa.py`：新增 `DELETE /api/qa/sessions/{id}`，校验 owner，物理删（级联删消息），返回 204。
- [ ] 5.6 owner 校验统一抽到模块内 `_get_owned_session(db, user, session_id) -> QASession`，404/403 在此抛出，避免路由重复代码。

## 6. 前端

- [ ] 6.1 `frontend/src/types.ts`：`QAAnswerOut` 新增 `session_id/session_title/message_id`；新增 `QASessionOut`/`QAMessageOut`/`QASessionDetailOut`/`QASessionPatchIn` 类型。
- [ ] 6.2 `frontend/src/api.ts`：`apiAskQuestion(question, sessionId?, sessionTitle?)` 支持可选入参；新增 `apiListQASessions`/`apiGetQASession`/`apiRenameQASession`/`apiDeleteQASession`。
- [ ] 6.3 `frontend/src/pages/TrustedQA.tsx`：左侧新增 320px 会话列表侧栏（新建/切换/重命名/删除），进入 `?s={id}` 时拉取该会话回放；当前 `messages` 从内存态改为「会话切换时 `apiGetQASession` 拉取 + 本轮 ask 返回后局部追加」；新建会话按钮清空当前。
- [ ] 6.4 保留现有打字机流式、引用卡片、检索面板、拒答警示——`QAMessageOut` 字段与 `QAAnswerOut` 对齐，复用渲染。
- [ ] 6.5 `Layout.tsx` 中 `/qa` 路径 sidebar 隐藏逻辑同步调整（避免新侧栏与全局 sidebar 重复）。

## 7. 验证

- [ ] 7.1 `openspec validate add-qa-session-history` 通过。
- [ ] 7.2 后端 import 自检：`cd labmemory-platform && python -c "from app.main import app"`。
- [ ] 7.3 启动后端 + 触发 `POST /api/qa/ask`（不带 session_id）→ 验证响应含 `session_id` 与 `message_id`，DB `qa_sessions`/`qa_messages` 各新增 1/2 条。
- [ ] 7.4 二次 ask 携带上轮 `session_id` → 验证 `QAMessage` 累计 4 条，`last_message_at` 已刷新。
- [ ] 7.5 跨用户 GET `/api/qa/sessions/{id}` → 验证 403。
- [ ] 7.6 前端 `npx tsc --noEmit` 通过；`npm run build` 通过。
- [ ] 7.7 现有测试 `pytest tests/test_hardening_smoke.py::test_qa_degrades_without_vector_not_503` 通过（向后兼容）。
- [ ] 7.8 `pytest tests/test_e2e.py` 全量通过。
- [ ] 7.9 `openspec archive add-qa-session-history --yes` 归档。
