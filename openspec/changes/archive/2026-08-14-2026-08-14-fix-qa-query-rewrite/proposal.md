# Proposal: fix-qa-query-rewrite（补实现查询改写并补入源真相规格）

## Why

对抗审查发现已归档 change `2026-08-13-add-qa-query-rewrite` 属虚标归档：tasks.md 全部勾选，但 rag.py/llm.py/前端无一行改写实现、声称的测试不存在、规格增量也未合入 `openspec/specs/decision-qa/spec.md`（grep「改写/search_query」零命中）。后果：多轮追问（「它的浓度是多少」）实际仍以原句检索 → 命不中 → 拒答，会话上下文对检索无效，违反 CLAUDE.md 第 0 节红线。

## What Changes

按原归档 change 的规格与任务清单**补齐实现**，并把其规格增量合入源真相：

1. `llm.py` 新增 `REWRITE_SYSTEM_PROMPT` + `rewrite_query(question, history)`（无历史/LLM 不可用/异常返回原问题；历史单条截断 500 字符；max_tokens=200、temperature=0.0）。
2. `rag.py:ask` 在状态过滤后、BM25 召回前加载历史并改写，`search_query` 用于召回，原 `question` 仍用于生成与落库；历史提前加载供生成阶段复用。
3. `retrieval_details.search_query` 透传成功路径与各拒答路径。
4. 前端 `types.ts` + `TrustedQA.tsx` 检索面板展示改写后查询。
5. `tests/test_hardening_smoke.py` 新增 `test_qa_multi_turn_query_rewrite`。

## Impact

- 代码：`app/services/llm.py`、`app/services/rag.py`、`frontend/src/types.ts`、`frontend/src/pages/TrustedQA.tsx`、`tests/test_hardening_smoke.py`
- 规格：decision-qa（ADDED 检索查询改写 + MODIFIED 历史上下文与检索边界、检索过程透明——沿用 2026-08-13 归档 change 的原文）
- 风险：低——无历史/降级路径行为与现状完全一致（不 worse）。
