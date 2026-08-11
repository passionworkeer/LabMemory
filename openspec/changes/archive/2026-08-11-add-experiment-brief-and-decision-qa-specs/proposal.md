## Why

labmemory-platform 已实现 `GET /api/experiments/{id}/brief`（实验简报）与 `POST /api/qa/ask`（可信知识问答）两个后端端点，但仓库根 `openspec/specs/` 的 14 个领域规格中均无对应条目，属于"先写代码、规格无兜底"，违反 CLAUDE.md「规格优先于代码」红线。本次补齐两块领域规格，使源真相覆盖与实现一致。

## What Changes

- **新增 `experiment-brief` 领域规格**：定义会前研讨包（实验当前上下文）的生成契约——当前主张、上一轮已发布结果、失败边界聚合、当前目标、资源与待办问题的组装规则与权限控制。
- **新增 `decision-qa` 领域规格**：定义可信知识问答的检索契约——权限前置过滤、状态过滤（仅 current 主张）、关键词匹配、带出处引用、无可靠证据时拒答。
- 仅补规格，**不改动任何实现代码与接口**（brief.py / qa.py 已按此行为运行，本次建立基线）。

## Capabilities

### New Capabilities
- `experiment-brief`: 实验会前研讨包——按实验维度组装当前主张、上一轮结果、失败边界、当前目标，供会议前浏览
- `decision-qa`: 可信知识问答——对当前有效主张做带权限、带状态过滤、带出处的检索式回答

### Modified Capabilities
<!-- 无既有规格需求发生变化 -->

## Impact

- 代码：无实现改动；仅新增 `openspec/specs/experiment-brief/spec.md` 与 `openspec/specs/decision-qa/spec.md`
- API：以现有 `GET /api/experiments/{id}/brief`、`POST /api/qa/ask` 为契约基线（行为不改，规格落地后经归档合入源真相）
- 依赖：无新依赖
