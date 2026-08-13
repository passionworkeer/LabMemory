## Why

可信问答虽已支持多轮历史（`QA_HISTORY_TURNS`），但**检索阶段完全基于原始问题**做 BM25/向量召回，不参考历史。当用户做指代性追问时（如第一轮"EXP-DEMO-001 温度"、第二轮"它的浓度是多少？"），检索用含指代词的原始问题查询，无法精准命中目标实体的目标属性切片，导致 LLM 因 context 缺失而拒答——用户体感为"AI 没记住上一轮"。

端到端复现：4 个多轮场景中 2 个拒答（"它的浓度"→拒答；"EXP-DEMO-002 呢"→拒答）。LLM 技术上"记住"了历史，但**检索没"记住"**，拿不到正确 context。

## What Changes

### 后端

- **新增查询改写** `app/services/llm.py`：`rewrite_query(question, history) -> str`，基于会话历史用专用 prompt 把指代性问题改写为自包含检索查询（补全实验编号/参数名等指代目标）。无历史、LLM 不可用或异常时返回原 question（降级为既有单轮检索，不 worse）。
- **检索前改写** `app/services/rag.py:ask`：在状态过滤之后、BM25/向量召回之前，加载会话历史并调用 `rewrite_query` 得到 `search_query`；用 `search_query` 做 BM25 + 向量召回，**原始 `question` 仍用于 LLM 生成与落库**。history 提前加载，生成阶段复用。
- **透明性**：`retrieval_details` 透传 `search_query`（成功与拒答路径），前端可展示实际检索查询。

### 前端

- **`frontend/src/types.ts`**：`QARetrievalDetails` 新增 `search_query?: string`。
- **`frontend/src/pages/TrustedQA.tsx`**：检索阶段面板在 `search_query` 与原始问题不同时展示「🔍 检索查询：{改写后查询}」行（hover 显示原问），让用户直观看到指代消解过程。

### 规格基线

- **ADDED** `openspec/specs/decision-qa/spec.md`：新增「检索查询改写」需求。
- **MODIFIED**：「历史上下文与检索边界」补充查询改写机制（历史用于生成自包含检索查询，检索仍单轮无状态）。
- **MODIFIED**：「检索过程透明」补充 `search_query` 透传。

## Capabilities

### Modified Capabilities
- `decision-qa`：多轮对话从"仅生成阶段带历史"升级为"检索前查询改写 + 生成阶段带历史"双轮驱动，解决指代性追问检索偏离。检索管线本体、权限过滤、拒答契约、降级路径、意图门控全部保持不变。

## Impact

- 代码：`labmemory-platform/app/services/llm.py`（`rewrite_query`）、`app/services/rag.py`（改写插入 + search_query 透传）、`frontend/src/pages/TrustedQA.tsx`、`frontend/src/types.ts`。**不动**：混合检索各阶段算法、索引器、引用后处理、会话持久化。
- API：`POST /api/qa/ask` 请求结构不变；`retrieval_details` 新增可选 `search_query` 字段。
- 成本：有历史的轮次多一次轻量 LLM 改写调用（max_tokens=200），远低于主生成成本；无历史/LLM 不可用时不触发。
- 安全/信任：改写只影响检索查询词，不放宽权限；改写 prompt 禁止引入历史中未提及的新实体；生成仍用原始 question + 真实检索 context，无信息泄漏面。
