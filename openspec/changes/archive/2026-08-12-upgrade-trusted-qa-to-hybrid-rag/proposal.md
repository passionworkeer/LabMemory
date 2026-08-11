## Why

PRD 8.6「可信知识问答」明确要求混合检索 = **结构化条件过滤 + BM25 + 向量 + 关系扩展 + Rerank**，并要求带出处回答、状态与版本过滤、无可靠证据时明确拒答。当前 `app/api/qa.py` 仅做关键词包含计数（仅检索 `Claim` 表 `current` 状态），无法回答语义相近但用词不同的问题，也无法引用 `Result` / `Evidence` / `FailureBoundary` 上的知识，更未接入大模型做归纳生成--与 PRD 要求存在显著差距。

本次升级在保留权限前置过滤与拒答契约的前提下，引入「混合检索 + 大模型生成」的 RAG 管线，使可信问答具备：

1. **语义检索能力**：用 Qwen 嵌入模型把 Claim/Result/Evidence/FailureBoundary 向量化，支持自然语言提问。
2. **关键词检索能力**：用 SQLite FTS5 BM25 兜底精确术语命中（实验编号、参数名、单位）。
3. **关系扩展**：命中 Claim 时自动带出支持该 Claim 的已发布 Result 与证据片段。
4. **重排**：BM25 + 向量相似度 + 时间新鲜度 + 状态权重做融合排序。
5. **大模型归纳**：DeepSeek-V4-Flash 基于检索上下文生成带引用的自然语言回答，拒答时显式列出需补充的条件。
6. **轻量化部署**：向量库选 sqlite-vec（SQLite 扩展，零外部服务），与现有 SQLite 单库架构一致；嵌入/对话走 API，无本地推理负担。

## What Changes

### 后端

- **新增嵌入服务** `app/services/embedding.py`：Qwen `text-embedding-v3`（DashScope API）客户端，无 API key 时回退到确定性 hash 伪向量（保证 demo 可运行）。
- **新增对话服务** `app/services/llm.py`：DeepSeek-V4-Flash（DeepSeek API）客户端，无 API key 时回退到模板式回答。
- **新增索引器** `app/services/indexer.py`：把 Claim（current）/ Result（published）/ Evidence（meeting transcript segments）/ FailureBoundary 切片写入 `EmbeddingChunk` 表 + sqlite-vec 向量表 + FTS5 倒排表；提供 `reindex_all()` 与增量 `index_claim/ index_result/ index_meeting`。
- **新增 RAG 编排** `app/services/rag.py`：权限前置过滤 → 状态过滤 → BM25 + 向量并行召回 → 关系扩展 → 重排 → 上下文组装 → LLM 生成 → 引用后处理。
- **新增向量库适配** `app/db/vec.py`：sqlite-vec 扩展加载、虚拟表 DDL、upsert/search 工具。
- **新增模型** `EmbeddingChunk`（`app/db/models.py`）：`chunk_id`、`chunk_type`、`ref_id`、`experiment_id`、`project_id`、`status`、`knowledge_status`、`content_text`、`metadata_json`、`embedding_model`、`content_hash`、`created_at`、`updated_at`。
- **重写** `app/api/qa.py`：调用 RAG 编排器，返回 `QAAnswerOut`（含 `answer`、`citations`、`retrieval_scope`、`refused`、新增 `retrieval_details` 与 `model_info`）。
- **扩展** `app/schemas.py` `QAAnswerOut`：新增 `retrieval_details`（各阶段命中数与 top score）、`model_info`（嵌入/对话模型名与降级标记）。
- **扩展** `app/config.py`：`QWEN_API_KEY`、`QWEN_EMBEDDING_MODEL`、`QWEN_EMBEDDING_DIM`、`DEEPSEEK_API_KEY`、`DEEPSEEK_CHAT_MODEL`、`RAG_TOP_K`、`RAG_MIN_SCORE`、`RAG_BM25_WEIGHT`、`RAG_VECTOR_WEIGHT`、`RAG_RECENCY_WEIGHT`、`RAG_STATUS_WEIGHT`、`RAG_ENABLE_LLM`。
- **接入索引触发点**：
  - `app/api/meetings.py` 复核确认后 → 索引 Claim + Evidence
  - `app/api/results.py` 结果发布后 → 索引 Result + FailureBoundary
  - `app/api/admin.py` reset-demo 后 → 全量重建索引
- **应用启动** `app/main.py`：启动时加载 sqlite-vec 扩展，确保虚拟表存在；首条提问前若索引为空则触发一次全量重建。

### 前端

- **重写** `frontend/src/pages/TrustedQA.tsx`：
  - 对话式 UI，AI 回答采用打字机效果（流式感知）
  - 引用卡片化展示：类型图标 + 标题 + 知识状态标签 + 跳转链接（主张→护照、结果→回流、证据→会议复核）
  - 检索范围面板升级：分阶段展示权限过滤 / 状态过滤 / BM25 召回 / 向量召回 / 关系扩展 / 重排 / LLM 各阶段命中数
  - 拒答时显式展示原因（无权限 / 无可匹配证据 / 分数过低 / 空问题）与需补充条件
  - 建议问题根据当前检索结果动态生成（命中主张的相邻主张）
- **扩展** `frontend/src/types.ts` `QAAnswerOut`：对齐后端新增字段。
- **扩展** `frontend/src/api.ts`：`apiAskQuestion` 支持新字段透传。

### 规格基线

- **新增** `openspec/specs/decision-qa/spec.md`（经归档合入源真相）：定义 RAG 问答的权限前置过滤、混合检索（BM25+向量+关系扩展+重排）、状态与版本过滤、带出处回答、明确拒答、模型降级、索引范围与切片、索引触发与失效等需求。

## Capabilities

### New Capabilities
- `decision-qa`: 可信知识问答--权限前置过滤 + 混合检索（BM25 + 向量 + 关系扩展 + 重排）+ LLM 归纳生成 + 带出处引用 + 无可靠证据明确拒答

### Modified Capabilities
<!-- decision-qa 此前无源真相规格，本次为首次建立 -->

## Impact

- 代码：新增 4 个后端服务文件、1 个数据库模型、1 个向量库适配；重写 qa.py 与 TrustedQA.tsx；扩展 schemas/config/api/types。所有改动均在 `labmemory-platform/` 内。
- API：`POST /api/qa/ask` 请求结构不变（仍为 `{question: string}`），响应结构扩展（新增 `retrieval_details`、`model_info`，原字段保留兼容）。
- 依赖：新增 `sqlite-vec>=0.1.6`、`dashscope>=1.20.0`（Qwen embedding SDK，可选）、`openai>=1.50.0`（DeepSeek 兼容 OpenAI SDK，可选）。无 API key 时自动降级到本地伪向量/模板回答，保证 demo 可运行。
- 数据：现有 SQLite 库增加 `embedding_chunks` 表、`vec_chunks` 虚拟表、`chunks_fts` 虚拟表；首次启动自动创建。
- 保密：嵌入/对话 API 调用仅发送脱敏的 Claim/Result/Evidence 文本，不发送用户凭证或会议原始妙记；与 CLAUDE.md「规格中不得写入真实妙记、Token、受限文档」一致。
