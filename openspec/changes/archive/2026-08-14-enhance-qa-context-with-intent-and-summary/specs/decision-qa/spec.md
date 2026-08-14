## MODIFIED Requirements

### Requirement: 大模型归纳生成

系统 SHALL 调用 DeepSeek-V4-Flash（或配置的兼容模型）基于 top-K 切片上下文生成自然语言回答。system prompt MUST 强制：仅基于提供的上下文回答、不得编造、每条结论标注 `[Cx]` 引用编号、无可靠证据时输出 `REFUSED: {reason}`。系统 SHALL 从 LLM 输出中提取 `[Cx]` 编号并映射回切片元数据组装 `citations`。

未配置 `DEEPSEEK_API_KEY` 或 `RAG_ENABLE_LLM=false` 时，系统 SHALL 降级为模板式回答（拼接 top-1 切片的结构化字段），并在 `model_info.chat_mode` 标记 `template_fallback`。

当请求携带有效 `session_id` 时，回答 agent 的 messages 数组 SHALL 按以下顺序组装：(1) system 提示词；(2) 若 `session.summary` 非空，追加一条 system 消息含 `<history_summary>` 块，并显式声明"仅用于消解指代与延续上下文，不得引用编号"；(3) 最近 `QA_HISTORY_TURNS` 轮完整 user/assistant 消息对（按 id 升序）；(4) 本轮 user 消息——当 `intent=="rag"` 时含 `<context>` 与 `<question>`，当 `intent=="chat"` 时仅含 `<question>`。历史消息文本 SHALL 在拼入 LLM 请求前按单条 2000 字符截断，超出追加 `[已截断]` 标记。`[Cx]` 编号 MUST 仅在本轮 `context_chunks` 内有效，历史轮与摘要中出现的编号 MUST NOT 出现在本轮 LLM 输出或 `citations` 中。

当 `intent=="chat"` 时，回答 agent SHALL 只基于上文 `history_summary` 与近几轮历史回答，不得虚构编号或切片；若上下文仍不足以回答，MUST 输出 `REFUSED: {原因}`。

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

#### Scenario: 历史消息条数受限

- GIVEN 会话 S1 已有 30 轮（60 条消息），`QA_HISTORY_TURNS=10`
- WHEN 用户在 S1 内追问新问题
- THEN 系统 SHALL 仅把最近 20 条历史消息（10 轮）拼入回答 agent 请求；更早消息 MUST 已被折叠进 `session.summary`，由摘要 system 消息承载

#### Scenario: 空补全降级而非空气泡

- GIVEN LLM 返回空 content（如 reasoning 耗尽 max_tokens，`finish_reason=length`）
- WHEN 系统处理生成结果
- THEN 系统 SHALL 视为生成失败并降级为模板式回答，`model_info.chat_mode='template_fallback'`，返回与落库的 `answer` MUST 非空

### Requirement: 历史消息持久化与回放

系统 SHALL 把每轮 Q&A（含拒答路径）以两条 `QAMessage`（`role=user` 与 `role=assistant`）持久化到 `qa_messages` 表。assistant 消息 MUST 完整保存 `citations_json`、`refused`、`retrieval_details_json`、`model_info_json`、`missing_conditions_json`，确保前端刷新后可无损回放对话流与检索面板。user 消息 SHALL 记录 `intent` 字段（`rag` / `chat`），用于回放与统计本轮是否触发过 RAG 检索。

`QASession` SHALL 维护 `summary`（折叠后的历史摘要正文，TEXT）与 `summary_cursor`（已折叠到的最大 `qa_messages.id`，幂等游标）。`summary` 非空时，前端会话详情 SHALL 返回该字段供渲染摘要横幅；`summary_cursor` SHALL 单调递增，禁止回退。

单会话消息数超过 `QA_SESSION_MAX_MESSAGES`（默认 200）时，最旧消息 SHALL 不可访问（保留在库但不进入详情响应），避免长会话内存膨胀。

#### Scenario: 刷新后回放完整对话

- GIVEN 会话 S1 已含 3 轮 Q&A，第 2 轮为拒答且第 2 轮 intent=chat
- WHEN 前端刷新页面并 GET `/api/qa/sessions/{S1.id}`
- THEN 响应 `messages` SHALL 含 6 条消息按 id 升序；第 2 轮 user 消息 `intent="chat"`，assistant 消息 `refused=true` 且 `missing_conditions` 完整还原；前端可重建原对话流、拒答警示框与意图标签

#### Scenario: 拒答也持久化

- GIVEN 用户提问「XYZ 实验」命中 0 切片触发拒答（intent=rag）
- WHEN 系统返回 `refused=true` 的同时
- THEN `qa_messages` SHALL 新增 user 消息（`intent="rag"`）与 assistant 消息各一条，assistant 消息 `refused=true` 且 `missing_conditions_json` 含原引导文案

#### Scenario: 摘要持久化可回放

- GIVEN 会话 S1 经历 15 轮对话后已折叠 5 轮，`summary="EXP-001 推荐 70℃..."`，`summary_cursor=10`
- WHEN 前端 GET `/api/qa/sessions/{S1.id}`
- THEN 响应 SHALL 含 `summary` 字段（非空字符串）与 `summary_cursor=10`；前端据此渲染"已折叠 5 轮早期对话"横幅

#### Scenario: 长会话限制可访问消息

- GIVEN 会话 S1 已有 250 条消息，`QA_SESSION_MAX_MESSAGES=200`
- WHEN GET `/api/qa/sessions/{S1.id}`
- THEN 响应 `messages` SHALL 仅含最近 200 条；前 50 条仍在库中但不返回

## ADDED Requirements

### Requirement: 意图识别 agent

系统 SHALL 在每轮 ask 解析会话后、检索前调用独立的意图识别 agent，输入本轮 `question` 与最近 2-4 条历史消息，输出 `{"intent": "rag" | "chat", "reason": "..."}` 严格 JSON。意图 agent SHALL 使用与回答 agent 独立的 system prompt，强制：需要查询实验主张/结果/证据/失败边界/参数版本判 `rag`；寒暄、致谢、闲聊、关于 agent 自身、用户明确说"不用查"判 `chat`；指代消解型追问若只需复述上文判 `chat`，若需新数据判 `rag`；模糊时倾向 `rag`。

当 `QA_ENABLE_INTENT=false` 时，系统 SHALL 跳过意图识别，所有问题直接走 RAG 检索（向后兼容降级）。

意图 agent LLM 不可用、JSON 解析失败或字段越界时，系统 SHALL 默认 `intent="rag"`（宁检索勿漏），并在 `retrieval_details.intent_reason` 标注 `fallback` 或 `parse_failed`。

当 `intent="chat"` 且 `QA_ENABLE_INTENT=true` 时，系统 SHALL 跳过 BM25/向量/关系扩展/重排整个检索管线，`context_chunks=[]`，`retrieval_details.skipped_by_intent=true`；回答 agent 仅基于摘要与历史生成回答。

#### Scenario: 检索意图触发 RAG

- GIVEN 用户在会话 S1 内提问「EXP-001 推荐温度」
- WHEN 意图 agent 输出 `{"intent":"rag","reason":"查询实验参数"}`
- THEN 系统 SHALL 走原检索管线，`retrieval_details.skipped_by_intent=false`，回答含 `[Cx]` 引用与 `citations`

#### Scenario: 闲聊意图跳过检索

- GIVEN 用户在会话 S1 内提问「谢谢你」
- WHEN 意图 agent 输出 `{"intent":"chat","reason":"致谢"}`
- THEN 系统 SHALL 跳过检索，`retrieval_details.skipped_by_intent=true`、`context_chunks=[]`、`citations=[]`，回答 agent 仅基于上文生成自然语言回应

#### Scenario: 指代消解走 chat 分支

- GIVEN 会话 S1 历史 assistant 已回答「EXP-001 推荐 70℃[C1] 由 R001 支持[C2]」
- WHEN 用户追问「把刚才那段用一句话复述」，意图 agent 输出 `{"intent":"chat","reason":"复述上文"}`
- THEN 系统 SHALL 跳过检索，回答中 MUST NOT 出现新 `[Cx]` 编号，`citations=[]`

#### Scenario: 意图 agent 降级默认 rag

- GIVEN 未配置 `DEEPSEEK_API_KEY`，`QA_ENABLE_INTENT=true`
- WHEN 用户提问「你好」
- THEN 意图 agent SHALL 默认 `rag`，`retrieval_details.intent_reason="fallback"`；后续走检索流程，可能因切片不匹配而拒答（不影响功能正确性）

#### Scenario: 关闭意图总开关

- GIVEN `QA_ENABLE_INTENT=false`
- WHEN 用户提问「你好」
- THEN 系统 SHALL 跳过意图 agent，直接走 RAG 检索（等价于升级前行为）

### Requirement: 历史滚动摘要

系统 SHALL 在每轮 ask 持久化后调用 `_maybe_summarize`：当会话未折叠消息数（`total_messages - summary_cursor 对应已折叠数`）超过 `QA_HISTORY_TURNS * 2 + 2` 时，把最旧的超出保留窗口的部分（按对齐到 user/assistant pair）经摘要 agent 折叠进 `session.summary`，并推进 `session.summary_cursor` 到被折叠的最后一条 message_id。

摘要 agent SHALL 使用独立 system prompt，要求中文输出 ≤300 字，必须保留实验编号、参数版本与具体数值（带单位）、知识状态、失败边界关键事实、已确立的指代对象、用户偏好或约束；必须丢弃寒暄、致谢、过程性措辞。摘要 agent 在已有 `session.summary` 时 SHALL 增量更新，不得丢失关键事实。

摘要 agent LLM 不可用时，系统 SHALL 不推进 `summary_cursor`，本轮多余消息按"超出窗口"形式被丢弃（不引入新风险），下一轮再试。摘要正文 SHALL 截断到 `QA_SUMMARY_MAX_CHARS`（默认 600）字符后存库。

折叠区间 MUST 对齐到完整 user/assistant pair：区间首条若为 assistant（说明对应 user 已折叠过）从第二条起取；区间末条若为 user（assistant 未生成）少取最后一条。

#### Scenario: 超窗口触发折叠

- GIVEN 会话 S1 有 24 条消息（12 轮），`QA_HISTORY_TURNS=10`、`summary_cursor=0`
- WHEN 第 13 轮 ask 完成持久化（共 26 条消息）
- THEN 系统 SHALL 把第 1-4 条消息（2 个 pair）折叠进 summary，`summary_cursor=4`，`summary` 非空

#### Scenario: 已折叠不重复折叠

- GIVEN 会话 S1 `summary_cursor=10`，共 26 条消息
- WHEN 第 14 轮 ask 完成（共 28 条）
- THEN 系统 SHALL 仅折叠第 11-? 条对齐 pair 的消息，MUST NOT 重复折叠 id<=10 的消息

#### Scenario: 摘要 agent 失败不推进游标

- GIVEN 会话 S1 满足折叠条件，但摘要 agent LLM 调用异常
- WHEN `_maybe_summarize` 执行
- THEN `session.summary` 与 `summary_cursor` SHALL 保持不变；本轮回答照常返回；下一轮 ask 时再次尝试

#### Scenario: 摘要内容保留关键事实

- GIVEN 折叠区间含「EXP-001 推荐 70℃ supported，失败边界 trigger=80℃ ruled_out=催化剂过量」
- WHEN 摘要 agent 生成 summary
- THEN summary SHALL 包含「EXP-001」「70℃」「supported」「失败边界 80℃」等关键 token，可被后续轮次 LLM 用于指代消解

#### Scenario: 摘要正文长度截断

- GIVEN 摘要 agent 输出 800 字
- WHEN 系统写入 `session.summary`
- THEN 存库值 SHALL 为前 600 字（`QA_SUMMARY_MAX_CHARS`），`summary_cursor` 仍推进
