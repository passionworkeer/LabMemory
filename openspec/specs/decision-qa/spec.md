# decision-qa Specification

## Purpose
可信知识问答：基于「权限前置过滤 + 混合检索（结构化条件 + BM25 + 向量 + 关系扩展 + 重排）+ 大模型归纳生成」的 RAG 管线，对实验当前有效主张、已发布结果、证据片段与失败边界做带出处的语义检索式回答；无可靠证据或范围不匹配时明确拒答并列出需补充条件，避免把未经证实或已废弃的结论当作答案。
## Requirements
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
系统 SHALL 在 `retrieval_details` 中返回各检索阶段的命中数与 top score，包含：`permission_filtered_experiments`、`status_filtered_chunks`、`bm25_hits`、`vector_hits`、`after_relation_expansion`、`after_rerank`、`top_score`。系统 SHALL 在 `model_info` 中返回 `embedding_mode`、`embedding_model`、`chat_mode`、`chat_model`、`top_k`。

#### Scenario: 前端展示检索阶段
- GIVEN 用户提问并命中 3 个切片
- THEN `retrieval_details` SHALL 包含各阶段命中数（如 `{permission_filtered_experiments: 2, status_filtered_chunks: 14, bm25_hits: 5, vector_hits: 8, after_relation_expansion: 10, after_rerank: 3, top_score: 0.78}`），前端可据此渲染检索范围面板

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

