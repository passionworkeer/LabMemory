# Tasks: fix-trust-rules-scenarios

## 1. 规格补齐

- [x] 1.1 为「任务状态机」补充 Scenario（已阻断任务不得请求飞书创建正式任务）
- [x] 1.2 为「三值留痕」补充 Scenario（人工修正记录修改人及原因）

## 2. 校验与归档

- [x] 2.1 `openspec validate fix-trust-rules-scenarios` 通过
- [x] 2.2 `openspec archive fix-trust-rules-scenarios --yes`（增量合入 `specs/trust-rules/spec.md`）
