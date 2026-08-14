## ADDED Requirements

### Requirement: 流式问答 SSE

系统 SHALL 提供 `POST /api/qa/ask/stream` 端点，请求体复用 `QAAskIn`，响应 `Content-Type: text/event-stream`，按后端处理阶段依次 emit 以下 SSE 事件（每事件格式 `event: <name>\ndata: <json>\n\n`）：

1. `session` — 会话解析（缺省新建）后立即 emit。data: `{session_id, session_title}`。
2. `intent` — 意图 agent 完成后 emit。data: `{intent: "rag" | "chat", reason}`。
3. `retrieval_started` — 仅 `intent="rag"` 路径 emit。data: `{}`。
4. `retrieval_completed` — 仅 rag 路径且检索未触发早期拒答时 emit。data: `{retrieval_details, citations, top_chunks}`（citations 为重排后全部 top-K 切片，前端可提前渲染引用卡片骨架）。
5. `answer_started` — 回答 LLM 调用前 emit。data: `{}`。
6. `answer` — 回答 LLM 完成后 emit。data: `{text, refused, missing_conditions, warning}`；拒答路径 emit `answer` 含 `refused=true` 与 `missing_conditions`。
7. `refused` — rag 路径下检索阶段触发早期拒答（`no_permission` / `no_match_after_status_filter` / `score_below_threshold`）时 emit。data: `{reason, missing_conditions, retrieval_details}`；emit 后跳过 `retrieval_completed` 与 `answer_started`，直接进入持久化与 `done`。
8. `done` — 持久化完成后 emit。data: 完整 `QAAnswerOut`（含 `session_id`、`message_id`、`session_title`、`model_info`、`retrieval_scope`、`retrieval_details`、`citations`、`refused`、`missing_conditions`）；前端据此回填最终状态。

事件顺序约束：`session` MUST 先于 `intent`；`intent` MUST 先于 `retrieval_started` / `answer_started`；`retrieval_started` MUST 紧跟 `retrieval_completed` 或 `refused`；`answer_started` MUST 紧跟 `answer`；`done` MUST 为最后一个事件。

降级路径：LLM 不可用时，`answer` 事件 `text` 为模板式回答；意图 agent 失败默认 `rag`，`intent` 事件 `reason="fallback"`。SSE 连接异常时（如客户端断开）后端 SHALL 静默终止生成器，MUST NOT 抛未处理异常。

`POST /api/qa/ask`（同步端点）行为 SHALL 保持不变，继续返回完整 `QAAnswerOut` JSON；流式端点与同步端点共用 `ask_stream_events` 生成器，逻辑零重复。

#### Scenario: rag 路径事件序列

- GIVEN 用户在会话 S1 内提问「EXP-001 推荐温度」，意图 agent 判 `rag`
- WHEN 客户端 POST `/api/qa/ask/stream`
- THEN 客户端 SHALL 依次收到 `session` → `intent(intent=rag)` → `retrieval_started` → `retrieval_completed` → `answer_started` → `answer` → `done` 共 7 个事件；`done.data.session_id` 与 `session.data.session_id` 一致

#### Scenario: chat 路径事件序列

- GIVEN 用户在会话 S1 内提问「谢谢你」，意图 agent 判 `chat`
- WHEN 客户端 POST `/api/qa/ask/stream`
- THEN 客户端 SHALL 依次收到 `session` → `intent(intent=chat)` → `answer_started` → `answer` → `done` 共 5 个事件；MUST NOT 收到 `retrieval_started` 或 `retrieval_completed`

#### Scenario: 检索阶段早期拒答

- GIVEN 用户提问「XYZ 实验」但无可匹配切片，意图 agent 判 `rag`
- WHEN 客户端 POST `/api/qa/ask/stream`
- THEN 客户端 SHALL 依次收到 `session` → `intent(rag)` → `retrieval_started` → `refused` → `done` 共 5 个事件；MUST NOT 收到 `retrieval_completed` / `answer_started` / `answer`；`done.data.refused=true`

#### Scenario: 空问题不走流式

- GIVEN 客户端 POST `/api/qa/ask/stream` body=`{question: ""}`
- WHEN 后端处理请求
- THEN 后端 SHALL emit `session` 与 `intent(reason=empty_question_skipped)` 后立即 emit `done(refused=true, reason=empty_question)`；或直接返回 400 JSON 错误（实现可选，MUST 不阻塞客户端）

#### Scenario: 前端按阶段切换打字机文案

- GIVEN 客户端发起 `/api/qa/ask/stream` 请求
- WHEN 收到 `intent(intent=rag)` 事件
- THEN 前端打字机文案 SHALL 切换为「检索中...」
- WHEN 收到 `retrieval_completed` 事件
- THEN 前端打字机文案 SHALL 切回「思考中...」
- WHEN 收到 `answer` 事件
- THEN 前端 SHALL 隐藏打字机并开始流式渲染 answer.text

#### Scenario: 同步端点行为不变

- GIVEN 客户端 POST `/api/qa/ask`（非流式）
- WHEN 后端返回响应
- THEN 响应 SHALL 为完整 `QAAnswerOut` JSON（与升级前一致），不返回 SSE 流；现有测试 `test_qa_degrades_without_vector_not_503` 与 `test_qa_smalltalk_skips_retrieval` 等仍通过

## MODIFIED Requirements

### Requirement: 大模型归纳生成

系统 SHALL 调用 DeepSeek-V4-Flash（或配置的兼容模型）基于 top-K 切片上下文生成自然语言回答。system prompt MUST 强制：仅基于提供的上下文回答、不得编造、每条结论标注 `[Cx]` 引用编号、无可靠证据时输出 `REFUSED: {reason}`。系统 SHALL 从 LLM 输出中提取 `[Cx]` 编号并映射回切片元数据组装 `citations`。

未配置 `DEEPSEEK_API_KEY` 或 `RAG_ENABLE_LLM=false` 时，系统 SHALL 降级为模板式回答（拼接 top-1 切片的结构化字段），并在 `model_info.chat_mode` 标记 `template_fallback`。

当请求携带有效 `session_id` 时，回答 agent 的 messages 数组 SHALL 按以下顺序组装：(1) system 提示词；(2) 若 `session.summary` 非空，追加一条 system 消息含 `<history_summary>` 块，并显式声明"仅用于消解指代与延续上下文，不得引用编号"；(3) 最近 `QA_HISTORY_TURNS` 轮完整 user/assistant 消息对（按 id 升序）；(4) 本轮 user 消息——当 `intent=="rag"` 时含 `<context>` 与 `<question>`，当 `intent=="chat"` 时仅含 `<question>`。历史消息文本 SHALL 在拼入 LLM 请求前按单条 2000 字符截断，超出追加 `[已截断]` 标记。`[Cx]` 编号 MUST 仅在本轮 `context_chunks` 内有效，历史轮与摘要中出现的编号 MUST NOT 出现在本轮 LLM 输出或 `citations` 中。

当 `intent=="chat"` 时，回答 agent SHALL 只基于上文 `history_summary` 与近几轮历史回答，不得虚构编号或切片；若上下文仍不足以回答，MUST 输出 `REFUSED: {原因}`。

当客户端请求 `POST /api/qa/ask/stream` 时，系统 SHALL 按阶段 emit SSE 事件（见「流式问答 SSE」需求），回答 agent 的生成结果通过 `answer` 事件传给前端；同步端点 `POST /api/qa/ask` 行为保持不变。两端点共用同一生成器实现，逻辑零重复。

#### Scenario: 多轮对话消解指代

- GIVEN 会话 S1 历史含 user「EXP-001 推荐温度」与 assistant「推荐温度为 70℃[C1]」
- WHEN 用户在 S1 内追问「它还有哪些失败边界」，意图 agent 判定 `intent=rag`
- THEN 系统 SHALL 把历史 2 条消息连同本轮检索到的 EXP-001 失败边界切片一起发给回答 agent；回答引用本轮切片并用 `[Cx]` 编号；`citations` SHALL 仅含本轮命中的失败边界切片

#### Scenario: 指代消解走 chat 分支不检索

- GIVEN 会话 S1 历史 user「EXP-001 推荐温度」与 assistant「推荐温度为 70℃[C1]，由 R001 支持[C2]」
- WHEN 用户在 S1 内追问「把刚才那段用一句话复述」，意图 agent 判定 `intent=chat`
- THEN 系统 SHALL 跳过 RAG 检索（`retrieval_details.skipped_by_intent=true`），回答 agent 仅基于摘要 + 历史生成回答，回答中 MUST NOT 出现新的 `[Cx]` 引用编号，`citations` 为空

#### Scenario: 摘要作为独立 system 消息注入

- GIVEN 会话 S1 已有 `summary="EXP-001 当前推荐 70℃，由 R001 支持；用户偏好只看 EXP-001 数据"`
- WHEN 用户在 S1 内提问
- THEN 回答 agent 的 messages 数组第 2 条 SHALL 为 system 消息含 `<history_summary>`，其内容 MUST 等于 S1.summary 截断后的文本

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

#### Scenario: 空补全降级而非空气泡

- GIVEN LLM 返回空 content（如 reasoning 耗尽 max_tokens，`finish_reason=length`）
- WHEN 系统处理生成结果
- THEN 系统 SHALL 视为生成失败并降级为模板式回答，`model_info.chat_mode='template_fallback'`，返回与落库的 `answer` MUST 非空

#### Scenario: 历史消息条数受限

- GIVEN 会话 S1 已有 30 轮（60 条消息），`QA_HISTORY_TURNS=10`
- WHEN 用户在 S1 内追问新问题
- THEN 系统 SHALL 仅把最近 20 条历史消息（10 轮）拼入回答 agent 请求；更早消息 MUST 已被折叠进 `session.summary`，由摘要 system 消息承载
