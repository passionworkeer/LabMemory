## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: 检索过程透明

系统 SHALL 在 `retrieval_details` 中返回各检索阶段的命中数与 top score，包含：`permission_filtered_experiments`、`status_filtered_chunks`、`bm25_hits`、`vector_hits`、`after_relation_expansion`、`after_rerank`、`top_score`。系统 SHALL 在 `model_info` 中返回 `embedding_mode`、`embedding_model`、`chat_mode`、`chat_model`、`top_k`。

凡是已执行检索的轮次（无论最终回答成功或拒答），`retrieval_details` SHALL 一致透传 `vector_available`，不得仅在成功路径返回。

当本轮被意图门控判定为直答（未执行检索）时，`retrieval_details` SHALL 改为返回 `retrieval_skipped=true` 与 `intent`（及 `elapsed_sec`），各阶段命中数字段 MUST NOT 以 0 值冒充真实检索结果；`model_info.embedding_mode` SHALL 标记为 `skipped`。前端 SHALL 据此展示「本轮无需检索」状态而非阶段计数。

#### Scenario: 前端展示检索阶段

- GIVEN 用户提问并命中 3 个切片
- THEN `retrieval_details` SHALL 包含各阶段命中数（如 `{permission_filtered_experiments: 2, status_filtered_chunks: 14, bm25_hits: 5, vector_hits: 8, after_relation_expansion: 10, after_rerank: 3, top_score: 0.78}`），前端可据此渲染检索范围面板

#### Scenario: 前端展示直答轮

- GIVEN 用户发送「你好」被直答
- THEN `retrieval_details` SHALL 含 `retrieval_skipped=true` 与 `intent='greeting'`，不含各阶段命中数；前端 SHALL 展示「意图识别 → 本轮无需检索，直接作答」

### Requirement: 大模型归纳生成

系统 SHALL 调用 DeepSeek-V4-Flash（或配置的兼容模型）基于 top-K 切片上下文生成自然语言回答。system prompt MUST 强制：仅基于提供的上下文回答、不得编造、每条结论标注 `[Cx]` 引用编号、无可靠证据时输出 `REFUSED: {reason}`。系统 SHALL 从 LLM 输出中提取 `[Cx]` 编号并映射回切片元数据组装 `citations`。

未配置 `DEEPSEEK_API_KEY` 或 `RAG_ENABLE_LLM=false` 时，系统 SHALL 降级为模板式回答（拼接 top-1 切片的结构化字段），并在 `model_info.chat_mode` 标记 `template_fallback`。

生成调用的 `max_tokens` SHALL 由配置项 `DEEPSEEK_MAX_TOKENS`（默认 4000）控制：推理型模型的 `reasoning_tokens` 计入 `completion_tokens`，预算不足时 content 会被截断为空串（`finish_reason=length`）。系统 MUST 将空补全（含 length 截断产生的空 content）视为生成失败并降级为模板式回答，MUST NOT 把空字符串作为回答返回或落库。

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

#### Scenario: 空补全降级而非空气泡

- GIVEN LLM 返回空 content（如 reasoning 耗尽 max_tokens，`finish_reason=length`）
- WHEN 系统处理生成结果
- THEN 系统 SHALL 视为生成失败并降级为模板式回答，`model_info.chat_mode='template_fallback'`，返回与落库的 `answer` MUST 非空

#### Scenario: 历史消息条数受限

- GIVEN 会话 S1 已有 20 条消息，`QA_HISTORY_TURNS=6`
- WHEN 用户在 S1 内追问新问题
- THEN 系统 SHALL 仅把最近 6 条历史消息拼入 LLM 请求，更早消息 MUST NOT 进入本次 LLM 调用
