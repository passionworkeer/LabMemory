## 1. scope 贯通

- [x] 1.1 `meetings.py:_build_claim`：`parameter_version["scope"]` 改用 `trust_rules._scope(chosen_candidate, modifications)`（候选回退）。
- [x] 1.2 `confirm_review`/`integration.py:card_callback` 的 `new_scope` 与 `_build_claim` 用同一来源。
- [x] 1.3 回归：候选带 scope 复核不带修改 → claim.scope == 候选 scope。

## 2. 语义栅栏

- [x] 2.1 `trust_rules.run_six_gates`：状态门扫描文本加入 `modifications.title` 与参数值文本。
- [x] 2.2 回归：`modifications={"title":"可以试试 70℃"}` → pending_validation。

## 3. 并发串行化

- [x] 3.1 `meetings.py:confirm_review`：`r.status != "pending"` 检查移入 `lock_experiment_for_write` 临界区。
- [x] 3.2 `tasks.py:audit_fix`、`run_audit` 写路径纳入实验写锁。

## 4. 启动复查版本

- [x] 4.1 `tasks.py:start_task`：复查绑定 claim 为实验 current 且 knowledge_status ∉ {refuted, replaced, insufficient_evidence}；不满足 → needs_confirmation + 修正提示。

## 5. 索引同步

- [x] 5.1 `meetings.py:confirm_review`：supersede 后调用 `mark_claim_superseded(db, old.claim_id)`；索引异常记 warning 日志。
- [x] 5.2 `integration.py:card_callback` approve 成功路径补 `index_claim`/`index_meeting`。
- [x] 5.3 回归：M001→M002 替代场景下 QA 检索不含旧主张切片。

## 6. supersede 按 scope + 数值统一

- [x] 6.1 `_build_claim`：supersede 目标改为「scope 等价（`_scope_eq`，None 仅匹配 None）的 current 集合」。
- [x] 6.2 参数继承判定用 `_value_key` 比较。
- [x] 6.3 `detect_conflicts` 的 supersede 排除集与新逻辑一致（同 scope 全部 current 中 created_at 最大者之外仍需检测；保持既有语义）。

## 7. 测试

- [x] 7.1 `tests/test_hardening_smoke.py` 新增：scope 贯通、栅栏扫修改值、启动版本复查、替代后旧切片排除（卡片路径）。
- [x] 7.2 `python -m pytest tests/ -q` 全绿；e2e 17 步全绿。
- [x] 7.3 `openspec validate` 通过后归档。
