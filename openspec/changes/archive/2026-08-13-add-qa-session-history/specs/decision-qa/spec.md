## MODIFIED Requirements

### Requirement: 大模型归纳生成

系统 SHALL 调用 DeepSeek-V4-Flash（或配置的兼容模型）基于 top-K 切片上下文生成自然语言回答。system prompt MUST 强制：仅基于提供的上下文回答、不得编造、每条结论标注 `[Cx]` 引用编号、无可靠证据时输出 `REFUSED: {reason}`。系统 SHALL 从 LLM 输出中提取 `[Cx]` 编号并映射回切片元数据组装 `citations`。

未配置 `DEEPSEEK_API_KEY` 或 `RAG_ENABLE_LLM=false` 时，系统 SHALL 降级为模板式回答（拼接 top-1 切片的结构化字段），并在 `model_info.chat_mode` 标记 `template_fallback`。

当请求携带有效 `session_id` 时，系统 SHALL 在调用 LLM 时附加该会话最近 `QA_HISTORY_TURNS` 条历史消息（按 `user`/`assistant` 角色交替排列在 system 与本轮 user 之间）。历史消息文本 SHALL 在拼入 LLM 请求前按单条 2000 字符截断，超出追加 `[已截断]` 标记。system prompt SHALL 补充规则：若用户问题引用上文实体（如「它/这个实验」），MUST 结合 history 消解指代；若 history 仍不足以消解，输出 `REFUSED: <原因>`。`[Cx]` 编号 MUST 仅对本轮 `context_chunks` 有效，历史轮引用编号 MUST NOT 出现在本轮 LLM 输出或 `citations` 中。

#### Scenario: 多轮对话消解指代

- GIVEN 会话 S1 历史含 user「EXP-001 推荐温度是多少」与 assistant「推荐温度为 70℃[C1]」
- WHEN 用户在 S1 内追问「它还有哪些失败边界」
- THEN 系统 SHALL 将该问题连同历史 2 条消息一起发给 LLM；LLM 输出 SHALL 引用本轮检索到的 EXP-001 失败边界切片并用 `[Cx]` 编号；`citations` SHALL 仅含本轮命中的失败边界切片，MUST NOT 复用上轮 C1 编号

#### Scenario: LLM 带引用生成

- GIVEN top-K 上下文含 [C1]=C003、[C2]=R001
- WHEN LLM 生成回答「实验推荐温度为 70℃[C1]，已由 R001 复现支持[C2]」
- THEN 系统 SHALL 提取 [C1] [C2]，`citations` 包含 2 条对应切片的引用对象

#### Scenario: LLM 主动拒答

- GIVEN 上下文与问题不相关或证据不足
- WHEN LLM 输出「REFUSED: 缺少 80℃ 相关证据」
- THEN 系统 SHALL 设 `refused=true`，`retrieval_scope.reason=llm_refused`，`missing_conditions` 包含「缺少 80℃ 相关证据」

#### Scenario: 无 API key 降级到模板

- GIVEN 未配置 `DEEPSEEK_API_KEY`
- WHEN 用户提问且检索命中 top-1 为 C003
- THEN 系统 SHALL 返回模板式回答（拼接 C003 的实验编号/主张 ID/参数版本/参数列表），`model_info.chat_mode='template_fallback'`，前端展示降级警告

#### Scenario: 历史消息条数受限

- GIVEN 会话 S1 已有 20 条消息，`QA_HISTORY_TURNS=6`
- WHEN 用户在 S1 内追问新问题
- THEN 系统 SHALL 仅把最近 6 条历史消息拼入 LLM 请求，更早消息 MUST NOT 进入本次 LLM 调用

## ADDED Requirements

### Requirement: 会话生命周期管理

系统 SHALL 提供会话级 Q&A 生命周期接口，按 `user_id` 严格隔离：

- `POST /api/qa/ask`：请求体接受可选 `session_id`（缺省时自动创建新会话）与可选 `session_title`（缺省时取首问前 30 字符）。响应 SHALL 返回 `session_id`、`session_title`、本轮 `message_id`。
- `GET /api/qa/sessions?limit=&offset=&include_archived=`：返回当前用户未归档会话列表，按 `last_message_at` 倒序分页。
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

### Requirement: 历史消息持久化与回放

系统 SHALL 把每轮 Q&A（含拒答路径）以两条 `QAMessage`（`role=user` 与 `role=assistant`）持久化到 `qa_messages` 表。assistant 消息 MUST 完整保存 `citations_json`、`refused`、`retrieval_details_json`、`model_info_json`、`missing_conditions_json`，确保前端刷新后可无损回放对话流与检索面板。

单会话消息数超过 `QA_SESSION_MAX_MESSAGES`（默认 200）时，最旧消息 SHALL 不可访问（保留在库但不进入详情响应），避免长会话内存膨胀。

#### Scenario: 刷新后回放完整对话

- GIVEN 会话 S1 已含 3 轮 Q&A，第 2 轮为拒答
- WHEN 前端刷新页面并 GET `/api/qa/sessions/{S1.id}`
- THEN 响应 `messages` SHALL 含 6 条消息按 id 升序，第 2 轮 assistant 消息 `refused=true` 且 `missing_conditions` 完整还原，前端可重建原对话流与拒答警示框

#### Scenario: 拒答也持久化

- GIVEN 用户提问「XYZ 实验」命中 0 切片触发拒答
- WHEN 系统返回 `refused=true` 的同时
- THEN `qa_messages` SHALL 新增 user 消息与 assistant 消息各一条，assistant 消息 `refused=true` 且 `missing_conditions_json` 含原引导文案

#### Scenario: 长会话限制可访问消息

- GIVEN 会话 S1 已有 250 条消息，`QA_SESSION_MAX_MESSAGES=200`
- WHEN GET `/api/qa/sessions/{S1.id}`
- THEN 响应 `messages` SHALL 仅含最近 200 条；前 50 条仍在库中但不返回

### Requirement: 历史上下文与检索边界

系统 SHALL 保持检索阶段单轮无状态：权限前置过滤、状态过滤、BM25 召回、向量召回、关系扩展、重排均 MUST 仅基于本轮 `question` 与请求者权限，MUST NOT 引入历史消息内容作为召回输入。历史消息 SHALL 仅在 LLM 生成阶段作为多轮上下文传入，用于指代消解与上下文延续。

权限过滤 MUST NOT 因历史消息中曾出现某 `experiment_id` 而放宽本轮权限范围；若本轮问题无可见实验相关切片，系统仍 SHALL 按既有拒答契约返回 `refused=true`。

#### Scenario: 检索不参考历史

- GIVEN 会话 S1 历史 user 消息含「EXP-001」，请求者对 EXP-001 仍无权限（被移出成员）
- WHEN 用户在 S1 内追问「它的失败边界」
- THEN 系统 SHALL 按当前权限过滤 EXP-001 出候选集，若无可匹配切片 MUST 返回 `refused=true, reason=no_match_after_status_filter`，MUST NOT 因历史出现 EXP-001 而放宽权限或越权召回

#### Scenario: 历史不参与召回

- GIVEN 会话 S1 历史 user 消息含「温度」关键词
- WHEN 用户在 S1 内追问「它还有哪些失败边界」（关键词与「温度」无关）
- THEN BM25 与向量召回 SHALL 仅基于本轮问题「它还有哪些失败边界」计算，MUST NOT 把「温度」纳入本轮召回查询
