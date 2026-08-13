## 1. 查询改写服务

- [x] 1.1 `app/services/llm.py`：新增 `REWRITE_SYSTEM_PROMPT`（补全指代实体与属性、只输出查询、保留原始意图、禁止引入新实体）。
- [x] 1.2 `app/services/llm.py`：新增 `rewrite_query(question, history) -> str`；无历史/LLM 不可用/异常时返回原 question（降级不 worse）；历史单条截断 500 字符；max_tokens=200、temperature=0.0。

## 2. RAG 检索前改写

- [x] 2.1 `app/services/rag.py:ask`：在状态过滤（步骤 2）之后、BM25 召回（步骤 3）之前，加载会话历史并调用 `llm.rewrite_query` 得到 `search_query`。
- [x] 2.2 用 `search_query` 替换 `question` 做 BM25（`fts_search`）与向量（`embed_query` + `vec_search`）召回；原始 `question` 仍用于 LLM 生成与落库。
- [x] 2.3 history 提前加载，步骤 8 生成阶段复用（删除原步骤 8 的重复加载）。
- [x] 2.4 `retrieval_details` 透传 `search_query`（成功路径 + ranked 空/score_below/llm_refused 拒答路径）。

## 3. 前端透明性

- [x] 3.1 `frontend/src/types.ts`：`QARetrievalDetails` 新增 `search_query?: string`。
- [x] 3.2 `frontend/src/pages/TrustedQA.tsx`：检索面板在 `search_query` 与原始问题不同时展示「🔍 检索查询」行（hover 显示原问）。

## 4. 测试与验证

- [x] 4.1 `tests/test_hardening_smoke.py`：新增 `test_qa_multi_turn_query_rewrite`，断言第二轮指代追问 `search_query` 透传且含被指代实体编号。
- [x] 4.2 端到端冒烟：4 多轮场景（浓度指代/跨实体/基础指代/原因追问）验证改写效果。
- [x] 4.3 `pytest tests/` 全量通过；前端 `tsc --noEmit` + `npm run build` 通过。
- [x] 4.4 归档：增量合入 `openspec/specs/decision-qa/spec.md`，change 移入 `archive/`。
