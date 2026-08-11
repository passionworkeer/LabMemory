## 背景

PRD 8.6 要求可信知识问答采用「结构化条件过滤 + BM25 + 向量 + 关系扩展 + Rerank」混合检索，并由大模型做带出处的归纳生成。本设计文档说明技术选型、索引范围、切片策略、检索流程、降级路径与数据模型，作为实现的工程依据。

## 1. 技术选型

### 1.1 向量数据库：sqlite-vec

**选择**：[sqlite-vec](https://github.com/asg0171/sqlite-vec)（SQLite 扩展，pip 包 `sqlite-vec`）。

**理由**：
- 项目当前用 SQLite 单库（`data/labmemory.db`），sqlite-vec 作为扩展加载到同一连接，零额外服务、零额外持久化路径。
- 支持 KNN 查询（`SELECT ... FROM vec_chunks WHERE embedding MATCH ? AND k = ?`），可与 SQL `WHERE` 子句组合做权限/状态前置过滤。
- 轻量：纯 C 扩展，无 Python 重依赖，安装即用。
- 与 FTS5（SQLite 内置 BM25）天然共存于同一连接，便于混合检索的 UNION 与 JOIN。

**对比**：
| 方案 | 优势 | 劣势 | 结论 |
|---|---|---|---|
| sqlite-vec | 零外部服务、与 SQLite 共存、轻量 | KNN 性能在百万级以下足够，超大库需迁移 | **选用** |
| ChromaDB | Python 友好、内置元数据过滤 | 独立持久化路径、需同步两套存储 | 过重 |
| FAISS | 性能极高 | 仅内存索引、无元数据存储、需自管映射 | 过底层 |
| LanceDB | 列式存储、向量化好 | 独立文件、生态较新 | 不必要 |

### 1.2 关键词检索：SQLite FTS5

SQLite 内置 FTS5 虚拟表，原生支持 BM25 排序函数 `bm25(chunks_fts)`。与 sqlite-vec 在同一连接内可联合查询，无需额外服务。

### 1.3 嵌入模型：Qwen text-embedding-v3

**选择**：阿里云 DashScope `text-embedding-v3`（1024 维）。

**调用**：通过 `dashscope` SDK 或直接 HTTP POST 到 `https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding`，请求体 `{model, input: [text]}`，响应取 `output.embeddings[i].embedding`。

**降级**：未配置 `QWEN_API_KEY` 时，回退到确定性 hash 伪向量：
- 对文本做 Unicode 码点累加 + 字符 n-gram hash，映射到 1024 维向量并 L2 归一化。
- 同一文本产生同一向量，相似文本因 n-gram 重叠产生相似向量（弱语义性，仅用于 demo）。
- 在 `model_info` 中标记 `embedding_mode="hash_fallback"`，前端提示「未配置 Qwen API key，使用伪向量」。

### 1.4 对话模型：DeepSeek-V4-Flash

**选择**：DeepSeek API（兼容 OpenAI SDK），模型名可配置，默认 `deepseek-chat`，可通过 `DEEPSEEK_CHAT_MODEL` 设置为 `deepseek-v4-flash` 等新模型。

**调用**：通过 `openai` SDK（`base_url="https://api.deepseek.com"`）发起 chat completions，system prompt 强制「仅基于提供的上下文回答，不得编造，每条结论标注 [Cxx] / [Rxx] / [Exx] 引用编号，无可靠证据时输出 `REFUSED`」。

**降级**：未配置 `DEEPSEEK_API_KEY` 或 `RAG_ENABLE_LLM=false` 时，回退到模板式回答（拼接 top-1 chunk 的结构化字段），在 `model_info` 中标记 `chat_mode="template_fallback"`。

## 2. 索引数据范围与切片策略

依据 PRD 第 6 章数据模型与第 8.6 节问答要求，对以下数据建索引：

| 切片类型 | 来源 | 筛选 | 切片粒度 | 主要字段 |
|---|---|---|---|---|
| `claim` | `Claim` 表 | `status='current'` | 1 主张 1 片 | claim_id, subject, predicate, object, conditions, parameter_version(version/key/value/unit/scope), knowledge_status, evidence(speaker/text) |
| `result` | `Result` 表 | `status='published'` | 1 结果 1 片 | result_id, actual_params, metrics, knowledge_status, failure_boundary 摘要, notes |
| `evidence` | `Meeting.transcript` 各段 | 已复核会议 | 1 段 1 片 | meeting_id, segment_index, speaker, start_offset_sec, text |
| `failure_boundary` | `Result.failure_boundary` | `Result.status='published'` 且 failure_boundary 非空 | 1 结果 1 片 | result_id, phenomenon, trigger_condition, root_cause_status, next_step |

**不索引**：Candidate（候选未确认）、Task（操作态）、ActionAudit（过程态）、MeetingReview（过程态）、AuditEvent（审计日志）--这些不构成可信知识，不应被问答引用。

**切片内容文本组装**（用于 embedding + BM25 索引）：
```
[claim C003 v2 current] 在 S1、0.20 mol/L、2h、Catalyst B 条件下，推荐温度为 70℃。
参数版本 v2：temperature=70℃, material=S1, concentration=0.20 mol/L, time=2h, catalyst=B。
知识状态：supported。
证据：陈工 00:08:32 "建议升到65度..."；EXP-0707-04 实验复现 78% 收率。
```

**元数据**（存 `metadata_json`，用于过滤与回显）：experiment_id、project_id、status、knowledge_status、claim_id/result_id/meeting_id、version、speaker、captured_at/published_at/effective_at。

## 3. 检索流程

```
用户提问 q
  ↓
[1 权限前置过滤] 取用户可见 experiment_id 集合 E（admin/pi 全量；其他角色按 ExperimentMember）
  ↓
[2 状态过滤] 候选 chunk 集合 = embedding_chunks WHERE experiment_id IN E
              AND status='current' (claim) 或 'published' (result)
              AND (knowledge_status IN (null,'supported','partially_supported') OR chunk_type IN ('evidence','failure_boundary'))
              注：pending_validation / refuted / superseded 默认排除
  ↓
[3 BM25 召回] SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 20
[4 向量召回]  SELECT chunk_id FROM vec_chunks WHERE embedding MATCH ? AND k=20
              两次召回 UNION（保留出现来源标记），各保留 top 20
  ↓
[5 关系扩展] 对召回的 claim chunk：拉取其支持结果（result chunk）+ 证据片段（evidence chunk），合并入候选集
  ↓
[6 重排] score = w_bm25·bm25_norm + w_vec·vec_sim + w_recency·recency + w_status·status_weight
         默认权重 0.35 / 0.35 / 0.15 / 0.15
         status_weight: supported=1.0, partially_supported=0.7, null=0.5, refuted=0.2
         取 top RAG_TOP_K (默认 5)
  ↓
[7 上下文组装] 把 top-K chunk 格式化为带编号的上下文：
              "[C1] claim C003 ... [C2] result R001 ... [C3] evidence M004#seg6 ..."
              同时构建 citation 索引表 {编号 -> chunk完整元数据}
  ↓
[8 LLM 生成] DeepSeek-V4-Flash，system prompt 强制带引用、拒答语义
             用户消息：问题 + 上下文
             若 LLM 输出含 "REFUSED" -> refused=true，提取其给出的缺补条件
  ↓
[9 后处理] 从 LLM 输出中提取 [Cx] 引用编号 -> 映射到 citation 索引表 -> 组装 citations 列表
          计算 retrieval_details（各阶段命中数 + top_score）
          计算 model_info（embedding_mode + chat_mode + 模型名）
  ↓
[10 返回] QAAnswerOut
```

## 4. 拒答逻辑

`refused=true` 当且仅当满足以下任一：
- 问题为空或仅空白字符
- 权限过滤后无可检索实验（`searched_experiments=0`）
- 状态过滤后候选 chunk 集为空
- 重排后 top score < `RAG_MIN_SCORE`（默认 0.25）
- LLM 输出包含 `REFUSED` 标记

拒答时 `answer` 字段给出引导文案，`retrieval_scope.reason` 标注具体原因（`empty_question` / `no_permission` / `no_match_after_status_filter` / `score_below_threshold` / `llm_refused`），并附 `missing_conditions` 提示需补充的实验编号/参数名/适用范围。

## 5. 索引触发与失效

| 事件 | 触发动作 |
|---|---|
| 复核确认（`POST /api/reviews/{id}/confirm` decision=confirmed） | 索引该会议生成的 Claim + Evidence |
| 结果发布（`POST /api/results` 状态变为 published） | 索引该 Result + FailureBoundary |
| 主张被替代（新 Claim 创建，旧 Claim status -> superseded） | 标记旧 Claim chunk 为 superseded（不删除，保留可追溯） |
| reset-demo（`POST /api/admin/reset-demo`） | 全量重建索引（drop + recreate + reindex_all） |
| 应用启动 | 确保 vec/fts 虚拟表存在；若 embedding_chunks 为空且 DB 有可索引数据，触发一次 reindex_all |

**幂等**：每个 chunk 以 `chunk_id`（如 `claim:C003`）为主键 upsert；`content_hash` 字段记录文本 sha256，若 hash 未变则跳过重新嵌入，节省 API 调用。

## 6. 数据模型

```python
class EmbeddingChunk(Base, IDMixin, TimestampMixin):
    __tablename__ = "embedding_chunks"
    chunk_id: str         # 'claim:C003' / 'result:R001' / 'evidence:M004#seg6' / 'boundary:R001'
    chunk_type: str       # 'claim' / 'result' / 'evidence' / 'failure_boundary'
    ref_id: str           # 原 ID（claim_id / result_id / meeting_id#seg / result_id）
    experiment_id: int    # FK experiments.id，用于权限过滤
    project_id: int       # FK projects.id
    status: str           # 'current' / 'superseded' / 'published' / 'frozen'
    knowledge_status: str | None  # 'supported' / 'partially_supported' / 'refuted' / None
    content_text: str     # 组装后的可读文本（用于 FTS 索引与 LLM 上下文）
    content_hash: str     # sha256(content_text)，用于幂等跳过
    metadata_json: dict   # 完整元数据（version/speaker/captured_at 等）
    embedding_model: str  # 'qwen-text-embedding-v3' / 'hash-fallback'
    # 向量本身存于 vec_chunks 虚拟表（rowid=embedding_chunks.id, embedding=BLOB）
```

**FTS5 虚拟表**：
```sql
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    chunk_id UNINDEXED, content_text, tokenize='unicode61'
);
```

**sqlite-vec 虚拟表**：
```sql
CREATE VIRTUAL TABLE vec_chunks USING vec0(
    embedding float[1024], chunk_id text
);
```

## 7. 前端交互

`TrustedQA.tsx` 重写要点：
- 顶部对话区：消息流式追加，AI 回答采用打字机效果（逐字 push 到 state，间隔 12ms/字符）。
- AI 消息内联引用卡片：每条引用独立一行，类型图标（📝 claim / 📊 result / 💬 evidence / ⚠️ boundary）+ 标题 + 知识状态标签 + 「查看」按钮跳转对应详情页。
- 右侧检索范围面板升级：垂直时间线展示 7 个阶段，每阶段显示命中数与 top score。
- 拒答状态：橙色警示框展示原因 + 缺补条件列表。
- 建议问题区：基于当前 top-1 命中主张，给出 3 个相邻主张的预生成问题（如「EXP-DEMO-001 还有哪些待验证主张？」）。
- 模型信息：底部小字显示 `embedding: qwen-text-embedding-v3 / chat: deepseek-v4-flash`，降级时显示警告。

## 8. 降级矩阵

| 场景 | embedding | chat | 行为 |
|---|---|---|---|
| 全配置（推荐） | Qwen API | DeepSeek API | 完整 RAG |
| 无 Qwen key | hash 伪向量 | DeepSeek API | 语义检索降级，仍 LLM 生成 |
| 无 DeepSeek key | Qwen API | 模板拼接 | 检索正常，回答为结构化模板 |
| 全部缺失 | hash 伪向量 | 模板拼接 | demo 可运行，前端提示降级 |
| `RAG_ENABLE_LLM=false` | Qwen API | 禁用 | 仅返回检索结果与原始 chunk 文本，不调用 LLM |

降级状态在 `model_info` 中显式标记，前端在 AI 消息下方显示「⚠️ 当前为降级模式：{具体说明}」。

## 9. 安全与权限

- 嵌入/对话 API 调用前，对内容做基本脱敏（移除明显 token、密钥模式），但 Claim/Result 本身为脱敏 demo 数据，无真实敏感信息。
- API key 仅在服务端使用，不下发前端；前端通过 `model_info.mode` 感知降级状态。
- 权限前置过滤在 SQL 层强制（`experiment_id IN (...)`），即使向量召回也无法绕过。
- 拒答时不泄露无权限内容的存在性（统一返回「无可匹配证据」）。

## 10. 与既有约定的关系

- **接口契约优先**：本次扩展 `QAAnswerOut` 字段为新增非破坏性，前端旧版本仍可工作（新字段缺失时 UI 隐藏对应区块）。
- **数据口径诚实**：检索指标在 `retrieval_details` 中如实展示各阶段命中数，不夸大效果。
- **保密**：API 调用日志默认不记录请求体；规格与文档中不写入真实妙记或 token。
