## 背景

`decision-qa` 规格已落地：权限前置过滤 + 混合检索 + LLM 归纳生成 + 拒答契约。但 LLM 调用始终是单轮 `system + 单 user`，前端 `messages` 仅在 React 内存里。本设计在不动检索管线的前提下补齐「会话生命周期 + 历史上下文承载」，并解决两个工程取舍：

1. **历史放在检索还是生成**：业界 RAG 最佳实践——检索保持单轮无状态，避免历史问题污染召回；历史仅用于 LLM 生成时的指代消解与本轮之外的常识补充。本项目遵循此实践。
2. **引用编号跨轮如何处理**：`[Cx]` 必须与当前传给 LLM 的本轮 `context_chunks` 一一对应；历史轮的 `[Cx]` 不可重出，否则 citation 映射会错位。本轮单独打包 context，引用编号在本轮独立编号。

## 1. 数据模型

### 1.1 QASession

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | int | PK | |
| user_id | int | FK(users.id), index | 严格隔离 |
| title | str(128) | not null | 首问前 30 字符，可改名 |
| archived | bool | default false | 软删归档（列表默认不显示） |
| last_message_at | datetime | nullable | 用于排序，每次追加消息时刷新 |
| created_at/updated_at | datetime | TimestampMixin | |

索引：`(user_id, archived, last_message_at DESC)` 便于列表分页排序。
外键级联：删除 `User` 时不级联（用户不可删，删除走 admin 重置流，那里已清全表）。删除 `QASession` 时 `ON DELETE CASCADE` 删 `QAMessage`。

### 1.2 QAMessage

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | int | PK | |
| session_id | int | FK(qa_sessions.id, ON DELETE CASCADE), index | |
| role | str(16) | not null | `user` / `assistant` |
| content | text | not null | 原始问题/回答文本 |
| citations_json | json | nullable | assistant 消息才填 |
| refused | bool | default false | assistant 消息才填 |
| retrieval_details_json | json | nullable | assistant 消息才填，前端可回放检索面板 |
| model_info_json | json | nullable | assistant 消息才填 |
| missing_conditions_json | json | nullable | 拒答时填 |
| created_at | datetime | TimestampMixin | 排序键 |

约束：`(session_id, id)` 复合排序保证消息顺序稳定。

### 1.3 表创建

`Base.metadata.create_all(bind=engine)` 已在 `app/main.py:lifespan` 中调用，新增模型自动建表，无需手写 migration。

## 2. 检索-生成-持久化编排

`rag.ask(db, user, question, session_id=None, session_title=None)` 流程：

```
1. 校验 question 非空        → 空问题拒答（不变）
2. ensure_index_ready(db)    → 不变
3. 权限前置过滤               → 不变（admin/pi 全量；其他按 ExperimentMember）
4. 状态过滤 → BM25 → 向量 → 关系扩展 → 重排  → 不变
5. 上下文组装（top-K chunks + [Cx] 编号）→ 不变
6. 会话解析：
   - session_id is None → 新建 QASession，title = session_title or question[:30]
   - session_id 给定   → 校验 user_id 匹配 + 未归档，否则 404/403
7. 历史载入：取该 session 最近 QA_HISTORY_TURNS 条 QAMessage（user+assistant 交替）
8. LLM 生成：调用 llm.chat_with_history(question, context_chunks, history)
   - messages = [system] + history_pairs + [本轮 user(含 <context> + question)]
   - 本轮 context 单独打包在最后一条 user 消息里，[Cx] 编号仅在本轮 context 内有效
9. 引用后处理（提取 [Cx] → 映射本轮 chunks）→ 不变
10. 持久化：
    - INSERT QAMessage(role=user, content=question)
    - INSERT QAMessage(role=assistant, content=answer, citations_json, refused, retrieval_details_json, model_info_json, missing_conditions_json)
    - UPDATE QASession.last_message_at = now
11. 返回 QAAnswerOut + session_id + session_title + message_id
```

**关键点**：拒答路径也持久化（用户应能看到自己提过的问题与拒答原因，便于补条件重试）。

## 3. LLM 多轮调用

`llm.chat_with_history(question, context_chunks, history) -> (text, mode)`：

- `history: list[dict]` 形如 `[{"role":"user","content":"..."}, {"role":"assistant","content":"..."}, ...]`，最多 `QA_HISTORY_TURNS` 条。
- 组装 `messages`：
  ```python
  messages = [{"role":"system","content": SYSTEM_PROMPT}]
  messages += history  # 已按 (user, assistant) 对齐
  messages.append({
      "role": "user",
      "content": f"<context>\n{context_text}\n</context>\n\n<question>\n{question}\n</question>\n\n请基于本轮 context 回答 question..."
  })
  ```
- `SYSTEM_PROMPT` 不变，但在末尾追加一条规则：「若用户问题引用了上文实体（如"它/这个实验"），MUST 结合 history 推断指代；若 history 仍不足以消解，输出 `REFUSED: <原因>`。」
- 降级路径：`_enabled=false` 或 API 异常 → 调用现有 `_template_answer`（不参考 history，保持简单）。

**token 预算**：单条消息文本超过 2000 字符截断保留前 2000 字符并追加 `[已截断]`；`QA_HISTORY_TURNS` 默认 6 条（3 轮 Q&A）。DeepSeek `max_tokens=800` 不变。

## 4. API 设计

| 路由 | 方法 | 入参 | 响应 | 权限 |
|---|---|---|---|---|
| `/api/qa/ask` | POST | `{question, session_id?, session_title?}` | `QAAnswerOut`（+`session_id/session_title/message_id`） | 登录用户 |
| `/api/qa/sessions` | GET | `?limit=20&offset=0&include_archived=false` | `list[QASessionOut]` | 登录用户（仅本人） |
| `/api/qa/sessions/{id}` | GET | — | `QASessionDetailOut`（含 `messages`） | 本人 |
| `/api/qa/sessions/{id}` | PATCH | `{title?, archived?}` | `QASessionOut` | 本人 |
| `/api/qa/sessions/{id}` | DELETE | — | `204` | 本人 |

权限校验统一在路由层：`session = db.get(QASession, id); if session.user_id != user.id: 403`，admin 不能跨用户访问他人 QA 会话（QA 内容可能含本人权限范围内才能看的实验上下文摘要，跨用户泄漏等于越权）。

## 5. 前端改造

`TrustedQA.tsx` 改造：

- 顶部新增左侧 320px 宽「会话列表」面板：
  - 「+ 新建会话」按钮 → 清空当前 messages，URL 清掉 `?s=`。
  - 会话项展示 title + last_message_at 相对时间，点击切换 → 调 `apiGetQASession(id)` 拉取并 setMessages。
  - 右键/按钮支持「重命名」「删除」（删除二次确认）。
- 进入 `/qa? s={id}` 时自动拉取该会话回放。
- 提问时携带当前 `sessionId`（可能为空 → 后端建会话后返回新 id → 前端 setSessionId 并更新 URL）。
- 现有打字机流式、引用卡片、检索面板、拒答警示全部保留——`QAMessageOut` 字段对齐 `QAAnswerOut`，可直接复用渲染逻辑。

## 6. 不引入的东西

- **不引入 query-rewrite 二次 LLM 调用**：成本/延迟翻倍，且历史上下文已能让 LLM 在生成阶段消解指代；检索仍用本轮原问题做 BM25/向量召回，召回率通过 system prompt 引导用户在追问里补足关键词即可。
- **不引入跨设备同步/WebSocket**：刷新即拉取已足够；多端同时编辑会话不是核心场景。
- **不引入向量缓存历史**：历史是会话级文本，不入向量索引；检索范围仍按 `EmbeddingChunk` 即可。
- **不引入 admin 跨用户审计视图**：QA 历史不进审计链（与 `AuditEvent` 解耦），保留未来扩展空间但不当前实现。

## 7. 兼容性与回退

- `POST /api/qa/ask` 请求字段向后兼容：旧前端不带 `session_id` 也能跑（自动建会话，前端不消费新字段也无所谓）。
- 现有测试 `tests/test_hardening_smoke.py::test_qa_degrades_without_vector_not_503` 不带 session_id，会自动建会话并返回答案 + 新字段，断言仍通过（断言只看 200 + 非空 answer）。
- 降级路径：LLM 不可用时仍走模板回答（不参考 history），会话仍能建/追加，仅是没有指代消解能力——与升级前体验一致。
