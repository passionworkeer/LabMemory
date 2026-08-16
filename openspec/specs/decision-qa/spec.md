# decision-qa Specification

## Purpose
可信知识问答：基于「权限前置过滤 + 混合检索（结构化条件 + BM25 + 向量 + 关系扩展 + 重排）+ 大模型归纳生成」的 RAG 管线，对实验当前有效主张、已发布结果、证据片段与失败边界做带出处的语义检索式回答；无可靠证据或范围不匹配时明确拒答并列出需补充条件，避免把未经证实或已废弃的结论当作答案。
## Requirements
### Requirement: 检索意图门控

系统 SHALL 在执行任何检索阶段之前对问题做意图分类（`greeting` / `thanks` / `goodbye` / `meta` / `knowledge`）。分类器 MUST 为确定性规则实现：对问题文本归一化（小写、压缩空白、剥离尾部标点与语气词）后，仅当整体与寒暄/元问题短语表完全匹配时才判定为非知识意图；其余输入一律判定为 `knowledge`。

被判定为非知识意图的输入 MUST NOT 触发任何检索阶段：不调用嵌入 API、不执行 BM25/向量召回、不做权限/状态过滤、不做关系扩展与重排，也 MUST NOT 触发索引就绪检查。系统 SHALL 直接生成简短友好作答：LLM 可用时经专用 smalltalk system prompt 生成（该 prompt MUST 禁止提及任何具体实验数据/结论、MUST 禁止输出 `[Cx]` 引用编号，并引导用户提出实验知识类问题）；LLM 不可用或异常时 SHALL 降级为按意图分类的固定模板文案。

意图门控 MUST fail-safe 向检索倾斜：寒暄与知识内容混合的输入（如「你好，EXP-001 温度是多少」）MUST 判定为 `knowledge` 并走完整混合检索管线。拿不准的输入 MUST 走检索。

直答轮次 SHALL 与检索轮次一样持久化（user + assistant 两条 `QAMessage`），`refused=false`、`citations=[]`，且 MUST NOT 影响既有拒答契约（空问题/无权限/无命中/低分/LLM 拒答判定逻辑不变）。

#### Scenario: 寒暄直答不触发检索

- GIVEN 用户 u_pi 已登录且有可见实验
- WHEN u_pi 提问「你好」
- THEN 系统 SHALL 返回 `refused=false`、`citations=[]` 的友好作答，`retrieval_details.retrieval_skipped=true` 且 `intent='greeting'`，全程 MUST NOT 调用嵌入 API 与 BM25/向量召回

#### Scenario: 感谢与告别直答

- GIVEN 用户在某会话内已有若干轮知识问答
- WHEN 用户发送「谢谢」或「再见」
- THEN 系统 SHALL 直答（`intent='thanks'`/`'goodbye'`），不执行检索，且本轮仍落库两条 `QAMessage`

#### Scenario: 助手能力询问直答

- GIVEN 用户提问「你能做什么」
- WHEN 系统判定 `intent='meta'`
- THEN 系统 SHALL 简要说明自身能力（基于主张/结果/证据/失败边界的带引用问答、证据不足拒答）并给出示例问题，MUST NOT 引用任何具体实验数据

#### Scenario: 混合内容 fail-safe 走检索

- GIVEN 用户提问「你好，EXP-DEMO-001 的推荐温度是多少」
- WHEN 意图分类器处理该输入
- THEN 系统 MUST 判定为 `knowledge` 并执行完整混合检索管线，MUST NOT 直答寒暄而忽略知识部分

#### Scenario: LLM 不可用时直答降级模板

- GIVEN 未配置 `DEEPSEEK_API_KEY` 或 LLM 调用异常
- WHEN 用户发送「你好」
- THEN 系统 SHALL 返回意图对应的固定模板文案，`model_info.chat_mode='template-fallback'`，`model_info.embedding_mode='skipped'`

#### Scenario: 无权限用户寒暄仍可直接作答

- GIVEN 用户 u_x 无任何可见实验
- WHEN u_x 发送「你好」
- THEN 系统 SHALL 直答问候（直答不访问任何实验数据，MUST NOT 返回 `no_permission` 拒答）；当 u_x 提问知识型问题时仍 SHALL 按既有契约返回 `refused=true, reason=no_permission`

### Requirement: 问答权限前置过滤
系统 SHALL 在检索前按请求者角色过滤可见实验：`admin` / `pi` 可见全部实验；其他角色 MUST 仅检索其作为成员（`ExperimentMember`）的实验。权限过滤 SHALL 在 SQL 层强制（`experiment_id IN (...)`），向量召回与 BM25 召回均 MUST NOT 绕过。无权内容不得出现在回答、引用或 `retrieval_details` 中。

#### Scenario: 非成员实验不出现在检索范围
- GIVEN 用户 u_web 角色为 executor 且仅属于实验 EXP-001
- WHEN u_web 提问内容与仅属于他人权限的 EXP-002 主张相关
- THEN 系统 SHALL 仅在 EXP-001 范围内检索，`retrieval_scope.searched_experiments` 为 1，EXP-002 的主张/结果/证据/失败边界均不会被匹配或引用

#### Scenario: 无任何可见实验时拒答
- GIVEN 用户 u_x 无任何 ExperimentMember 关联且非 admin/pi
- WHEN u_x 提问任意问题
- THEN 系统 SHALL 返回 `refused=true`，`retrieval_scope.reason=no_permission`，`missing_conditions` 包含「无可见实验，请联系 PI 加入项目」

### Requirement: 索引范围与切片
系统 SHALL 对以下数据建索引，每条记录产出 1 个切片（evidence 按会议逐字稿段切片）：
- `Claim` 表中 `status='current'` 的主张
- `Result` 表中 `status='published'` 的结果
- 已复核会议（`MeetingReview.status='processed'` 且 `decision='confirmed'`）的 `Meeting.transcript` 各段证据
- 已发布结果中非空的 `Result.failure_boundary`

系统 MUST NOT 索引 Candidate / Task / ActionAudit / MeetingReview / AuditEvent / `status='superseded'` 的主张 / `status='frozen'` 的结果。

#### Scenario: 主张被索引为切片
- GIVEN 实验 EXP-001 有 current 主张 C003 与 superseded 主张 C001
- WHEN 系统执行索引
- THEN `embedding_chunks` SHALL 包含 `chunk_id='claim:C003'` 一条，MUST NOT 包含 `chunk_id='claim:C001'`

#### Scenario: 已发布结果与失败边界被索引
- GIVEN 实验 EXP-001 有 published 结果 R001（含 failure_boundary）
- WHEN 系统执行索引
- THEN `embedding_chunks` SHALL 包含 `chunk_id='result:R001'` 与 `chunk_id='boundary:R001'` 两条

#### Scenario: 证据按段切片
- GIVEN 会议 M004 已复核确认，transcript 含 8 段发言
- WHEN 系统执行索引
- THEN `embedding_chunks` SHALL 包含 8 条 `chunk_type='evidence'`，`chunk_id` 形如 `evidence:M004#seg0` ~ `evidence:M004#seg7`

### Requirement: 切片内容组装
系统 SHALL 为每个切片组装可读文本用于嵌入与 BM25 索引，文本 MUST 包含切片类型标识、原 ID、关键参数/指标/条件、知识状态与证据摘要。系统 SHALL 同时维护 `content_hash`（sha256 of content_text）用于幂等跳过：当切片内容未变时 MUST NOT 重新调用嵌入 API。

#### Scenario: 主张切片文本包含参数版本
- GIVEN 主张 C003 含 parameter_version={version:'v2', key:'temperature', value:'70', unit:'℃', scope:{material:'S1'}}
- WHEN 系统组装切片文本
- THEN 文本 SHALL 包含「C003」「v2」「temperature」「70」「℃」「S1」等关键 token

#### Scenario: 内容未变跳过嵌入
- GIVEN 主张 C003 已索引，content_hash=H1
- WHEN 触发重新索引且 C003 内容未变
- THEN 系统 MUST NOT 调用嵌入 API，仅保留现有向量

### Requirement: 混合检索
系统 SHALL 对用户问题执行混合检索，按以下顺序：
1. 权限前置过滤（见「问答权限前置过滤」）
2. 状态过滤：候选集 = current 主张 + published 结果 + 已复核会议证据 + 失败边界；默认排除 `knowledge_status='refuted'` 与 `status='superseded'`/`'frozen'`
3. BM25 召回：FTS5 MATCH，取 top 20
4. 向量召回：sqlite-vec KNN，取 top 20
5. 关系扩展：对召回的 claim 切片，拉取其支持结果与证据片段合并入候选
6. 重排：`score = w_bm25·bm25_norm + w_vec·vec_sim + w_recency·recency + w_status·status_weight`，默认权重 0.35/0.35/0.15/0.15，取 top `RAG_TOP_K`（默认 5）

`status_weight` SHALL 取值：supported=1.0、partially_supported=0.7、null=0.5、refuted=0.2。

#### Scenario: 语义相近用词不同仍可命中
- GIVEN 主张 C003 切片文本为「推荐温度为 70℃」
- WHEN 用户提问「这个实验合适的温度是多少度」
- THEN 向量召回 SHALL 命中 C003（余弦相似度高于阈值），即使无关键词字面交集

#### Scenario: BM25 兜底精确术语命中
- GIVEN 用户提问「EXP-DEMO-001 的 C003 主张」
- WHEN 系统 BM25 召回
- THEN FTS5 SHALL 命中含「EXP-DEMO-001」「C003」的切片，得分高于其他切片

#### Scenario: 关系扩展带入支持结果
- GIVEN 主张 C003 被结果 R001（published, supported）支持
- WHEN 向量召回命中 C003 但未直接命中 R001
- THEN 关系扩展 SHALL 把 R001 切片合并入候选集，最终 citations MAY 包含 R001

### Requirement: 状态与版本过滤
系统 SHALL 默认仅检索 `status='current'` 的主张与 `status='published'` 的结果。`knowledge_status` 默认优先级为 `supported` > `partially_supported` > `null`；`pending_validation` / `refuted` / `superseded` 默认排除。当 top-1 命中为 `knowledge_status='pending_validation'` 或 `null` 时，系统 SHALL 在回答中显式提示「该结论尚未经实验结果验证，仅作参考」。

#### Scenario: 旧版本主张不作为答案
- GIVEN 实验 EXP-001 中主张 C001（80℃，superseded）与 C003（70℃，current）并存
- WHEN 用户询问「温度是多少」
- THEN 系统 SHALL 仅以 C003 作答，MUST NOT 返回 C001

#### Scenario: 待验证主张需显式提示
- GIVEN 主张 C005 知识状态为 null（候选已确认但无结果支持）
- WHEN 用户提问命中 C005 为 top-1
- THEN 回答 SHALL 包含「该结论尚未经实验结果验证，仅作参考」提示，`retrieval_scope.warning` 标注 `unvalidated_claim`

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

### Requirement: 嵌入模型与降级
系统 SHALL 默认使用 Qwen `text-embedding-v3`（DashScope API，1024 维）。未配置 `QWEN_API_KEY` 时 SHALL 降级为确定性 hash 伪向量（同文本同向量、相似文本弱语义相似），并在 `model_info.embedding_mode` 标记 `hash_fallback`。

#### Scenario: Qwen API 正常调用
- GIVEN 已配置 `QWEN_API_KEY`
- WHEN 系统嵌入文本「推荐温度 70℃」
- THEN 嵌入向量 SHALL 为 1024 维浮点数组，`model_info.embedding_mode='qwen-text-embedding-v3'`

#### Scenario: 无 key 降级到 hash 伪向量
- GIVEN 未配置 `QWEN_API_KEY`
- WHEN 系统嵌入相同文本两次
- THEN 两次产生的向量 SHALL 完全一致（确定性），`model_info.embedding_mode='hash_fallback'`，前端展示降级警告

### Requirement: 带出处引用
系统 SHALL 在回答中附带结构化引用列表，每条引用包含 `type`（claim/result/evidence/failure_boundary）、`ref_id`、`title`、`knowledge_status`（如适用）、`url`（跳转链接：claim->`/passport/{experiment_id}`、result->`/result/{task_id}`、evidence->`/review/{meeting_id}`、failure_boundary->`/result/{task_id}`）、`metadata`（version/speaker/captured_at/task_id 等）。`task_id` SHALL 通过切片 metadata 获取，若 metadata 缺失则 MUST 通过 `ref_id`（result_id）回查 `results.task_id` -> `tasks.task_id` 获取。引用顺序 SHALL 与 LLM 输出中 `[Cx]` 出现顺序一致。

#### Scenario: 命中时附带引用
- GIVEN LLM 输出含 [C1] [C2] [C3] 三个引用
- THEN `citations` SHALL 为 3 元素列表，依次对应 C1/C2/C3 的切片元数据，每条含 `url` 可跳转

#### Scenario: result 引用跳转到对应任务详情
- GIVEN 命中 result 切片 ref_id=R001，关联 task_id=TSK-001
- THEN `citations[i].url` SHALL 为 `/result/TSK-001`，点击后跳转到结果回流详情页

#### Scenario: 旧索引 fallback 回查
- GIVEN 命中 result 切片 metadata 不含 task_id（旧索引）
- THEN 系统 SHALL 通过 `ref_id`（result_id）查询 `results` 表获取数字 `task_id`，再查询 `tasks` 表获取字符串 `task_id`，组装 `/result/{task_id}` URL

### Requirement: 明确拒答
系统 SHALL 在以下任一情况返回 `refused=true`：
- 问题为空或仅空白字符（`reason=empty_question`）
- 权限过滤后无可检索实验（`reason=no_permission`）
- 状态过滤后候选切片集为空（`reason=no_match_after_status_filter`）
- 重排后 top score < `RAG_MIN_SCORE`（默认 0.25）（`reason=score_below_threshold`）
- LLM 输出 `REFUSED`（`reason=llm_refused`）

拒答时 `answer` SHALL 给出引导文案，`missing_conditions` SHALL 列出需补充的条件（实验编号/参数名/适用范围/具体证据类型）。

#### Scenario: 空问题拒答
- GIVEN 用户提交空字符串或仅空白字符
- THEN 响应 SHALL 为 `refused=true`，`retrieval_scope.reason='empty_question'`

#### Scenario: 无可匹配证据拒答
- GIVEN 用户提问「XYZ 实验」但所有可见实验无相关切片
- THEN 响应 SHALL 为 `refused=true`，`reason='no_match_after_status_filter'` 或 `'score_below_threshold'`，`missing_conditions` 提示「未找到 XYZ 实验相关证据，请确认实验编号或补充参数名称」

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

### Requirement: 索引触发与失效
系统 SHALL 在以下事件触发索引更新：
- 会议复核确认（`decision='confirmed'`）-> 索引该会议生成的 Claim 与 Evidence
- 结果发布（`status` 变为 `published`）-> 索引该 Result 与 FailureBoundary
- 主张被替代（新 Claim 创建，旧 Claim `status` 变 `superseded`）-> 旧 Claim 切片 `status` 标记为 `superseded`（MUST NOT 删除，保留可追溯）
- reset-demo -> 全量重建索引
- 应用启动且 `embedding_chunks` 为空且 DB 有可索引数据 -> 触发一次 `reindex_all`

#### Scenario: 复核确认触发索引
- GIVEN 会议 M004 复核 status=pending
- WHEN 用户调用 `POST /api/reviews/M004/confirm` decision=confirmed，生成主张 C003
- THEN 系统 SHALL 在响应返回前完成 C003 与 M004 证据段的索引，`embedding_chunks` 含新切片

#### Scenario: 结果发布触发索引
- GIVEN 结果 R001 status=submitted
- WHEN 用户调用 `POST /api/results` 发布 R001 为 published
- THEN 系统 SHALL 索引 R001 切片与（如有）boundary 切片

#### Scenario: 主张被替代标记旧切片
- GIVEN 旧主张 C001 已索引，新主张 C003 创建并 replaces C001，C001 status -> superseded
- WHEN 索引更新完成
- THEN `claim:C001` 切片 `status` SHALL 变为 `superseded`，后续问答检索 MUST NOT 命中该切片，但切片记录仍保留在 `embedding_chunks` 中

### Requirement: 应用启动初始化
系统 SHALL 在应用启动时加载 sqlite-vec 扩展、确保 `vec_chunks` 与 `chunks_fts` 虚拟表存在、并在 `embedding_chunks` 为空但 DB 含可索引数据时自动触发 `reindex_all`。建表 SHALL 独立处理两类虚拟表：`chunks_fts`（FTS5，SQLite 内置）MUST 始终建成功；`vec_chunks`（vec0，依赖 sqlite-vec 扩展）建表失败时系统 SHALL 不影响 `chunks_fts` 的创建。启动失败 MUST NOT 阻止应用启动。`vec_chunks` 不可用时，`POST /api/qa/ask` SHALL 降级为仅 BM25 + 关系扩展 + 重排（跳过向量召回）并返回结果（而非 503），且在 `retrieval_details.vector_available` 标注 `false`；仅当 `chunks_fts` 也不可用时才拒答。

#### Scenario: 首次启动自动建表与建索引
- GIVEN 全新 SQLite 库，无 `embedding_chunks` / `vec_chunks` / `chunks_fts`
- WHEN 应用首次启动
- THEN 系统 SHALL 创建上述三张表，若 DB 已含 Claim/Result 数据则触发 `reindex_all`，`embedding_chunks` 非空

#### Scenario: sqlite-vec 扩展加载失败降级
- GIVEN sqlite-vec 扩展无法加载（如未安装）
- WHEN 用户调用 `POST /api/qa/ask`
- THEN 系统 SHALL 完成 BM25 召回 + 关系扩展 + 重排并返回答案（而非 503），`retrieval_details.vector_available=false`、`vector_hits=0`，前端可据此展示「向量检索不可用，已降级为关键词检索」提示

### Requirement: 关系扩展的证据关联键
系统 SHALL 在混合检索的「关系扩展」阶段，以**字符串** `meeting_id`（`Meeting.meeting_id`）关联 claim 的支持证据片段（evidence 切片 `ref_id` 形如 `{meeting_id}#seg{idx}`）；MUST NOT 用整数外键（`Claim.meeting_id` 指向 `Meeting.id`）直接拼接 ref_id，否则 SHALL 不命中任何证据切片、关系扩展静默失效。

#### Scenario: claim 命中后带入其会议证据
- GIVEN 主张 C003 命中向量/BM25 召回，其所属会议 M004 的逐字稿已被索引为 `evidence:M004#seg0..7`
- WHEN 关系扩展处理 C003
- THEN 系统 SHALL 经 `Meeting` 将 C003 的整数 meeting FK 解析为字符串 `meeting_id`，至少把一条 `evidence:M004#seg{idx}` 合并入候选集

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

### Requirement: 状态与版本过滤的索引时效

检索候选集的 claim 切片状态 MUST 与主张生命周期同步：主张被 supersede 时，其检索切片 SHALL 同步标记 superseded（不得继续以 current 参与召回）；主张 knowledge_status 变为 refuted/replaced/insufficient_evidence 时，其切片 SHALL 同步刷新并因状态过滤被排除。

#### Scenario: 替代后旧版本不参与召回

- GIVEN 实验 E 主张 C1（80℃）已索引为 current，新复核发布 C2（70℃）替代 C1
- WHEN 用户提问「当前推荐温度」
- THEN 检索候选集 SHALL 含 C2 的切片且不含 C1 的切片

### Requirement: 拒答轮模型信息诚实

已执行嵌入/检索的拒答轮（score 低于阈值、检索未命中等），`model_info` SHALL 反映本轮实际使用的嵌入与生成模式，不得固定回退为 hash-fallback/template-fallback。

#### Scenario: 阈值拒答的真实模式

- GIVEN 本轮以真实向量嵌入执行检索，因 top_score 低于阈值拒答
- THEN model_info.embedding_mode SHALL 为本轮实际嵌入模式，而非 hash-fallback

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

