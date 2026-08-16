## MODIFIED Requirements

### Requirement: 会话生命周期管理

系统 SHALL 提供会话级 Q&A 生命周期接口，按 `user_id` 严格隔离：

- `POST /api/qa/ask`：请求体接受可选 `session_id`（缺省时自动创建新会话）与可选 `session_title`（缺省时取首问前 30 字符）。响应 SHALL 返回 `session_id`、`session_title`、本轮 `message_id`。
- `GET /api/qa/sessions?limit=&offset=&include_archived=`：返回当前用户未归档会话列表，按 `last_message_at` 倒序分页。每项含 `message_count`；该计数 MUST 由单条聚合查询（`GROUP BY session_id`）一次取得，MUST NOT 对每个会话单独发 COUNT 查询（N+1）。
- `GET /api/qa/sessions/{id}`：返回该会话基本信息及全部 `QAMessage`（按 `id` 升序）。
- `PATCH /api/qa/sessions/{id}`：支持 `{title?, archived?}` 局部更新。
- `DELETE /api/qa/sessions/{id}`：物理删除会话及其全部消息（`ON DELETE CASCADE`），不进入审计链。

系统 MUST 校验 `session.user_id == 请求者.id`，否则返回 403。admin MUST NOT 跨用户访问他人 QA 会话。

#### Scenario: 不带 session_id 自动建会话

- GIVEN 用户 u_pi 已登录，前端首次提问「EXP-001 推荐温度」
- WHEN 前端 POST `/api/qa/ask` body=`{question:"EXP-001 推荐温度"}`（无 session_id）
- THEN 系统 SHALL 新建 `QASession(user_id=u_pi.id, title="EXP-001 推荐温度")`，响应含 `session_id` 为新会话 ID 与 `session_title`，前端据此切换到该会话上下文

#### Scenario: 携带 session_id 追加历史

- GIVEN 用户 u_pi 持有会话 S1（user_id 匹配，未归档）
- WHEN 前端 POST `/api/qa/ask` body=`{question:"它有哪些失败边界", session_id:"S1"}`
- THEN 系统 SHALL 把本轮 user 消息与 assistant 消息分别追加为 `QAMessage(session_id=S1.id, ...)`，刷新 `QASession.last_message_at`，响应 `session_id` 与请求一致

#### Scenario: 跨用户访问会话被拒

- GIVEN 会话 S1 属于 u_pi
- WHEN u_executor（非 admin）尝试 GET `/api/qa/sessions/{S1.id}`
- THEN 系统 SHALL 返回 403，MUST NOT 暴露 S1 的标题、消息或存在性

#### Scenario: 重命名与归档

- GIVEN 用户 u_pi 持有会话 S1
- WHEN PATCH `/api/qa/sessions/{S1.id}` body=`{title:"温度调研", archived:true}`
- THEN 系统 SHALL 更新 S1.title 与 S1.archived，后续 `GET /api/qa/sessions` 默认列表 MUST NOT 包含 S1（除非 `include_archived=true`）

#### Scenario: 删除会话级联清消息

- GIVEN 会话 S1 有 8 条 QAMessage
- WHEN DELETE `/api/qa/sessions/{S1.id}`
- THEN 系统 SHALL 物理删除 S1 及其 8 条消息，返回 204；后续 GET `/api/qa/sessions/{S1.id}` SHALL 返回 404

#### Scenario: 会话列表单次聚合计数

- GIVEN 用户 u_pi 持有 20 个会话、共 200 条消息
- WHEN GET `/api/qa/sessions?limit=20`
- THEN 系统 SHALL 以不超过 2 条 SQL 完成列表与全部 `message_count`，响应结构与逐会话计数实现完全一致
