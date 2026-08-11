## 1. 后端基础设施

- [x] 1.1 `app/config.py`：新增 `QWEN_API_KEY`、`QWEN_EMBEDDING_MODEL`、`QWEN_EMBEDDING_DIM`、`DEEPSEEK_API_KEY`、`DEEPSEEK_CHAT_MODEL`、`DEEPSEEK_BASE_URL`、`RAG_TOP_K`、`RAG_MIN_SCORE`、`RAG_BM25_WEIGHT`、`RAG_VECTOR_WEIGHT`、`RAG_RECENCY_WEIGHT`、`RAG_STATUS_WEIGHT`、`RAG_ENABLE_LLM` 配置项；`.env.example` 同步
- [x] 1.2 `app/db/vec.py`：sqlite-vec 扩展加载（`conn.enable_load_extension` + `load_extension`）、`ensure_vec_tables()` 创建 `vec_chunks` 虚拟表、`vec_upsert(rowid, chunk_id, embedding)`、`vec_search(embedding, k, where_clause)` 工具
- [x] 1.3 `app/db/models.py`：新增 `EmbeddingChunk` 模型（chunk_id 唯一索引、experiment_id 外键、content_hash 索引）
- [x] 1.4 `app/db/base.py`：`init_db()` 中调用 `ensure_vec_tables()`；`Base.metadata.create_all` 后调用 FTS5 虚拟表创建
- [x] 1.5 `requirements.txt`：新增 `sqlite-vec>=0.1.6`、`dashscope>=1.20.0`、`openai>=1.50.0`

## 2. 嵌入与对话服务

- [x] 2.1 `app/services/embedding.py`：`embed_texts(texts: list[str]) -> list[list[float]]`；优先 DashScope API（批量 25 条/请求），失败或无 key 时回退 hash 伪向量；返回 `(embeddings, mode)` 元组
- [x] 2.2 `app/services/llm.py`：`chat(messages: list[dict]) -> str`；优先 DeepSeek API（openai SDK，base_url=deepseek），无 key 或 `RAG_ENABLE_LLM=false` 时返回 `__TEMPLATE__` 哨兵；`build_qa_prompt(question, context_chunks) -> list[dict]` 组装 system+user 消息
- [x] 2.3 system prompt 设计：强制「仅基于上下文回答、每条结论带 [Cx] 引用、无可靠证据输出 `REFUSED: {reason}`」

## 3. 索引器

- [x] 3.1 `app/services/indexer.py`：
  - `_build_claim_text(claim) -> str`：组装主张切片文本
  - `_build_result_text(result) -> str`：组装结果切片文本
  - `_build_evidence_text(meeting, seg) -> str`：组装证据切片文本
  - `_build_boundary_text(result) -> str`：组装失败边界切片文本
- [x] 3.2 `index_claim(db, claim_id)` / `index_result(db, result_id)` / `index_meeting(db, meeting_id)` / `index_failure_boundary(db, result_id)`：单条 upsert（content_hash 跳过）
- [x] 3.3 `mark_claim_superseded(db, claim_id)`：旧主张 chunk status -> superseded
- [x] 3.4 `reindex_all(db)`：清空 `embedding_chunks` + `vec_chunks` + `chunks_fts`，全量重建（仅 current/published 数据）
- [x] 3.5 `ensure_index_ready(db)`：若 `embedding_chunks` 为空且 DB 有可索引数据，触发 `reindex_all`

## 4. RAG 编排

- [x] 4.1 `app/services/rag.py` `ask(db, user, question) -> QAAnswerOut`：
  - 步骤 1：权限前置过滤（admin/pi 全量；其他按 ExperimentMember）
  - 步骤 2：状态过滤 SQL（status + knowledge_status）
  - 步骤 3：BM25 召回（FTS5 MATCH，top 20）
  - 步骤 4：向量召回（vec_search，top 20）
  - 步骤 5：关系扩展（claim -> result + evidence）
  - 步骤 6：重排（score = 加权和，取 top RAG_TOP_K）
  - 步骤 7：上下文组装（带 [Cx] 编号）
  - 步骤 8：LLM 生成（或模板降级）
  - 步骤 9：引用后处理（提取 [Cx] -> 映射 chunk）
- [x] 4.2 拒答逻辑：空问题 / 无权限 / 无匹配 / 低分 / LLM REFUSED 五种场景，分别标注 `retrieval_scope.reason` 与 `missing_conditions`
- [x] 4.3 `retrieval_details` 组装：各阶段命中数与 top score
- [x] 4.4 `model_info` 组装：embedding_mode / chat_mode / 模型名

## 5. API 与 Schema

- [x] 5.1 `app/schemas.py`：扩展 `QAAnswerOut` 新增 `retrieval_details: dict`、`model_info: dict`、`missing_conditions: list[str] = []`；新增 `QACitationOut` 子结构（type/ref_id/title/knowledge_status/url/metadata）
- [x] 5.2 `app/api/qa.py`：重写为调用 `rag.ask()`，移除关键词逻辑；保留路由 `POST /api/qa/ask` 与请求结构
- [x] 5.3 `app/main.py` startup：加载 sqlite-vec 扩展、`ensure_vec_tables()`、`ensure_index_ready()`
- [x] 5.4 `app/api/meetings.py`：复核确认后调用 `index_claim` + `index_meeting`（证据段）
- [x] 5.5 `app/api/results.py`：结果发布后调用 `index_result` + `index_failure_boundary`
- [x] 5.6 `app/api/admin.py`：reset-demo 后调用 `reindex_all`
- [x] 5.7 `scripts/seed_demo.py`：seed 完成后调用 `reindex_all`

## 6. 前端

- [x] 6.1 `frontend/src/types.ts`：扩展 `QAAnswerOut` 新增 `retrieval_details`、`model_info`、`missing_conditions`、`citations` 结构化
- [x] 6.2 `frontend/src/api.ts`：`apiAskQuestion` 透传新字段
- [x] 6.3 `frontend/src/pages/TrustedQA.tsx` 重写：
  - 对话流式追加（打字机效果）
  - 引用卡片化（类型图标 + 标题 + 知识状态 + 跳转链接）
  - 检索范围面板升级（7 阶段时间线 + 命中数）
  - 拒答橙色警示框 + 缺补条件列表
  - 模型信息底部显示 + 降级警告
  - 建议问题动态生成

## 7. 验证

- [x] 7.1 `openspec validate upgrade-trusted-qa-to-hybrid-rag` 通过
- [x] 7.2 后端 `python -c "from app.main import app"` import 自检
- [x] 7.3 前端 `npx tsc --noEmit` 类型检查通过
- [x] 7.4 前端 `npm run build` 构建通过
- [x] 7.5 手动验证：启动后端 + 前端，提典型问题，确认检索/引用/降级路径正常
- [x] 7.6 `openspec archive upgrade-trusted-qa-to-hybrid-rag --yes` 归档
