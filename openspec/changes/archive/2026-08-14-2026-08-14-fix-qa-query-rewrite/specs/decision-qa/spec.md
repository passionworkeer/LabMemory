## ADDED Requirements

### Requirement: 检索查询改写

系统 SHALL 在 BM25/向量召回之前，当存在会话历史时，基于历史把当前问题改写为一个自包含的独立检索查询（补全指代实体如实验编号、参数名与隐含属性）。改写 SHALL 由 LLM 经专用 system prompt 完成，该 prompt MUST 禁止引入历史中未提及的新实体或新问题，且仅输出改写后的查询本身。

改写后的查询 SHALL 用于 BM25 与向量召回；原始问题 SHALL 仍用于 LLM 生成与消息落库。无会话历史（首轮）、LLM 不可用或改写异常时，系统 SHALL 直接使用原始问题检索（降级为既有单轮行为，不得 worse）。

系统 SHALL 在 `retrieval_details` 中透传 `search_query`（实际用于检索的查询），前端可据此展示指代消解过程。

#### Scenario: 指代性追问改写后精准命中

- GIVEN 会话 S1 历史含 user「EXP-DEMO-001 当前推荐温度是多少」与 assistant「推荐温度为 70℃」
- WHEN 用户在 S1 内追问「它的浓度是多少」
- THEN 系统 SHALL 将查询改写为含「EXP-DEMO-001」与「浓度」的自包含查询，用该查询做 BM25/向量召回，`retrieval_details.search_query` 透传改写后查询

#### Scenario: 首轮无历史不触发改写

- GIVEN 用户首次提问（无会话历史）
- WHEN 用户提问「EXP-DEMO-001 当前推荐温度是多少」
- THEN 系统 SHALL 直接用原始问题检索，`search_query` 缺省或等于原始问题

#### Scenario: LLM 不可用降级原问题检索

- GIVEN 未配置 `DEEPSEEK_API_KEY` 或改写 LLM 调用异常
- WHEN 用户在多轮会话内做指代追问
- THEN 系统 SHALL 用原始问题做检索（不因改写失败而中断），`search_query` 等于原始问题

## MODIFIED Requirements

### Requirement: 历史上下文与检索边界

系统 SHALL 保持检索阶段单轮无状态：权限前置过滤、状态过滤均 MUST 仅基于本轮请求者权限，MUST NOT 引入历史消息内容作为召回输入。

历史消息 SHALL 在两个阶段使用：（1）检索前查询改写——基于历史生成自包含检索查询，改写后的查询作为独立单轮查询参与 BM25/向量召回（检索本身仍只看单一查询，不把历史直接喂给召回）；（2）LLM 生成阶段作为多轮上下文传入，用于指代消解与上下文延续。

权限过滤 MUST NOT 因历史消息中曾出现某 `experiment_id` 而放宽本轮权限范围；查询改写 MUST NOT 引入历史中未提及的新实体。若本轮问题无可见实验相关切片，系统仍 SHALL 按既有拒答契约返回 `refused=true`。

#### Scenario: 检索不参考历史

- GIVEN 会话 S1 历史 user 消息含「EXP-001」，请求者对 EXP-001 仍无权限（被移出成员）
- WHEN 用户在 S1 内追问「它的失败边界」
- THEN 系统 SHALL 按当前权限过滤 EXP-001 出候选集，若无可匹配切片 MUST 返回 `refused=true`，MUST NOT 因历史出现 EXP-001 而放宽权限或越权召回

#### Scenario: 历史不参与召回

- GIVEN 会话 S1 历史 user 消息含「温度」关键词
- WHEN 用户在 S1 内追问「它还有哪些失败边界」（关键词与「温度」无关）
- THEN BM25 与向量召回 SHALL 仅基于改写后的单一检索查询计算（改写保留追问意图、仅补全指代实体），MUST NOT 把历史消息原文或历史关键词直接拼接进召回查询

### Requirement: 检索过程透明

系统 SHALL 在 `retrieval_details` 中返回各检索阶段的命中数与 top score，包含：`permission_filtered_experiments`、`status_filtered_chunks`、`bm25_hits`、`vector_hits`、`after_relation_expansion`、`after_rerank`、`top_score`，并透传 `search_query`（实际用于 BM25/向量召回的查询，可能经查询改写与原始问题不同）。系统 SHALL 在 `model_info` 中返回 `embedding_mode`、`embedding_model`、`chat_mode`、`chat_model`、`top_k`。

凡是已执行检索的轮次（无论最终回答成功或拒答），`retrieval_details` SHALL 一致透传 `vector_available`，不得仅在成功路径返回。

当本轮被意图门控判定为直答（未执行检索）时，`retrieval_details` SHALL 改为返回 `retrieval_skipped=true` 与 `intent`（及 `elapsed_sec`），各阶段命中数字段 MUST NOT 以 0 值冒充真实检索结果；`model_info.embedding_mode` SHALL 标记为 `skipped`。前端 SHALL 据此展示「本轮无需检索」状态而非阶段计数。

#### Scenario: 前端展示检索阶段
- GIVEN 用户提问并命中 3 个切片
- THEN `retrieval_details` SHALL 包含各阶段命中数（如 `{permission_filtered_experiments: 2, status_filtered_chunks: 14, bm25_hits: 5, vector_hits: 8, after_relation_expansion: 10, after_rerank: 3, top_score: 0.78}`），前端可据此渲染检索范围面板

#### Scenario: 前端展示直答轮

- GIVEN 用户发送「你好」被直答
- THEN `retrieval_details` SHALL 含 `retrieval_skipped=true` 与 `intent='greeting'`，不含各阶段命中数；前端 SHALL 展示「意图识别 → 本轮无需检索，直接作答」

#### Scenario: 前端展示改写后查询
- GIVEN 用户做指代追问，查询被改写（`search_query` 与原始问题不同）
- THEN `retrieval_details.search_query` SHALL 为改写后的自包含查询，前端 SHALL 展示「检索查询（指代已消解）」行让用户看到指代消解过程
