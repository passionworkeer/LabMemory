# Tasks: refine-numeric-conflict-supersede

## 1. 规格修订

- [x] 1.1 MODIFIED「冲突检测」：数值冲突界定为「未被本次 supersede 替换的多 current 并存」；补「复核确认替换单条 current 不视为数值冲突」Scenario
- [x] 1.2 MODIFIED「发布前冲突检测」：同步界定 + 把「数值冲突冻结发布」Scenario 改写为「真正多 current 并存才冻结」；补「复核确认替换不冻结」Scenario
- [x] 1.3 `openspec validate refine-numeric-conflict-supersede` 通过

## 2. 实现对齐

- [x] 2.1 `app/services/trust_rules.py` `detect_conflicts`：数值冲突循环排除「将被本次发布 supersede 的最新 current」（与 `_build_claim` 的 supersede 目标选择一致：`status=current order by created_at desc`）
- [x] 2.2 `labmemory-platform/scripts/e2e_test.py` 第二次会议改为「值变更（temperature 70→72）」验证 supersede + 升版，不再回避数值冲突；并断言新主张 status==current（非冻结）

## 3. 校验与归档

- [x] 3.1 `openspec validate refine-numeric-conflict-supersede` 通过
- [x] 3.2 `openspec archive refine-numeric-conflict-supersede --yes`（增量合入 `specs/trust-rules/spec.md`）

## 4. 端到端验证

- [x] 4.1 `pytest tests/test_e2e.py` 通过（值变更 supersede 为 current，未冻结）
