## 1. 查询改写服务

- [x] 1.1 `app/services/llm.py`：新增 `REWRITE_SYSTEM_PROMPT`（补全指代实体与属性、只输出查询、保留原始意图、禁止引入新实体）。
- [x] 1.2 `app/services/llm.py`：新增 `rewrite_query(question, history) -> str`；无历史/LLM 不可用/异常时返回原 question；历史单条截断 500 字符；max_tokens=200、temperature=0.0。

## 2. RAG 检索前改写

- [x] 2.1 `app/services/rag.py:ask`：状态过滤后、BM25 召回前加载会话历史并调用 `llm.rewrite_query` 得到 `search_query`。
- [x] 2.2 `search_query` 用于 `fts_search` 与 `embed_query`+`vec_search`；原始 `question` 仍用于 LLM 生成与落库。
- [x] 2.3 history 提前加载，生成阶段复用（删除步骤 8 的重复加载）。
- [x] 2.4 `retrieval_details` 透传 `search_query`（成功 + ranked 空/score_below/llm_refused 路径）。

## 3. 前端透明性

- [x] 3.1 `frontend/src/types.ts`：`QARetrievalDetails` 新增 `search_query?: string`。
- [x] 3.2 `frontend/src/pages/TrustedQA.tsx`：检索面板在 `search_query` 与原始问题不同时展示「检索查询」行。

## 4. 测试与验证

- [x] 4.1 `tests/test_hardening_smoke.py`：新增 `test_qa_multi_turn_query_rewrite`。
- [x] 4.2 `pytest tests/` 全量通过；前端 `npm run build` 通过。
- [x] 4.3 归档：增量合入 `openspec/specs/decision-qa/spec.md`。
