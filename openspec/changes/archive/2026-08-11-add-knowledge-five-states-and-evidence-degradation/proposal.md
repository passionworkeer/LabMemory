# Proposal: 知识状态 5 态 + 证据失效降级

## Why

AUDIT T2-7/T2-3：`ResultPublishIn.knowledge_status` 仅 3 态（supported/partially_supported/refuted），缺 PRD §10.6 的 `replaced`（替代）与 `insufficient_evidence`（证据不足）；证据失效降级（PRD §13.1）完全未实现——证据锚点入库后永不复验，失效后仍被问答检索推荐。

## What Changes

- **T2-7**：`ResultPublishIn.knowledge_status` Literal 扩展为 5 态（+ `replaced` / `insufficient_evidence`，PRD §10.6）。`Claim.knowledge_status` / `Result.knowledge_status` 字段已是字符串，无 schema 迁移。
- **T2-3**：新增 `app/services/evidence.py::validate_evidence(claim)` 结构化校验（evidence 非空且每条有 text 视为有效；空/残缺→invalid）。
  - 发布结果时：若主张证据失效，仅允许 `knowledge_status=insufficient_evidence`（自动建议）。
  - 问答 `/api/qa/ask`：排除证据失效的 current 主张（停止主动推荐，PRD §13.1）。
  - 真实 URL 可达性探活需真飞书文档权限（demo 用占位 URL），本次实现结构化校验 + 接线，URL 探活记入路线图。

## Impact

- spec 增量：MODIFY `result-backflow`（5 态）、ADDED 证据失效降级 requirement（入 `decision-inbox`）。
- 代码：`app/schemas.py`（Literal 扩展）、`app/services/evidence.py`（新）、`app/api/qa.py`（排除失效）、`app/api/results.py`（发布时校验）。
- 回归：平台 e2e/pytest/cross_side 全绿（e2e 发布 partially_supported 仍合法）。
