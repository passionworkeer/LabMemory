# Proposal: 可信规则引擎（六道闸门 + 冲突检测 + 语义栅栏）

## Why

第一性原理审查（见 `AUDIT.md` T2-1/T2-2/T2-6）发现：候选→主张发布路径**零闸门**——`confirm_review` 与 `card_callback approve` 直接 `_build_claim` 生成 `current` 主张；"六道闸门"只是任务执行前的 5 项审计（`_run_checks`），与候选发布闸门是两件事；6 类冲突检测仅剩版本对比；"可以试试/暂定"等语义可直接生效。

PRD §10.1（六道闸门）、§10.5（冲突检测规则）、line 854（语义栅栏）明确定义了规则。本 change 据此实现独立的**可信规则引擎**，在候选→主张发布前强制运行，未过则主张降级为「待补充/待验证」而非 `current`。

## What Changes

- **新增** `app/services/trust_rules.py`：
  - `run_six_gates(candidate, modifications, experiment, reviewer)` —— 对象门/参数门/证据门/范围门/状态门/责任门（PRD §10.1），返回 `{gates, failed, publish_status, passed}`。
  - `detect_conflicts(...)` —— 6 类冲突（版本/数值/范围/语义/证据/责任，PRD §10.5），返回冲突清单。
  - `SEMANTIC_HEDGE_KEYWORDS`（可以试试/建议/可能/暂定/试试/或许/考虑）用于状态门 + 语义栅栏（PRD line 854）。
- **修改** `Claim.status` 取值扩展：`current` / `superseded` / `pending_supplement`（待补充）/ `pending_validation`（待验证）。
- **修改** `app/api/meetings.py:confirm_review` 与 `app/api/integration.py:card_callback`：`_build_claim` 后运行六闸门 + 冲突检测；未过则 claim 置 `pending_supplement`/`pending_validation`，**不生成任务草稿**（或任务直接 blocked），响应携带闸门/冲突报告。
- **修改** 问答 `app/api/qa.py` 与护照：仅 `current` 主张参与（`pending_*` 不作为答案/当前主张，但可审计查看）。
- **不修改** 任务执行前的 `_run_checks`（它是「行动前审计」，与「候选发布闸门」职责分离，各自保留）。

## 规则（PRD 推导）

六道闸门（任一失败→不发布为 current）：
- **对象门**：候选有 `experiment_ref` 且实验存在 → 失败→待补充
- **参数门**：`parameters` 非空且每项有 `name`+`value`（+`unit` 若数值）→ 失败→待补充
- **证据门**：`evidence` 非空且每条有 `text` → 失败→待验证（证据不足）
- **范围门**：有 `scope`（材料/催化剂/浓度等边界）→ 失败→待补充
- **状态门**：标题/描述不含暂定/建议关键词 → 命中→待验证（语义栅栏）
- **责任门**：reviewer/actor 为实验成员 → 失败→待补充

冲突检测（发布前跨主张检查）：
- **数值冲突**：同 `scope` 同参数名已有 `current` 不同值 → 冻结发布
- **范围冲突**：新结论 scope 与任务条件不匹配 → 阻断/降级
- **版本冲突**：复用 `_run_checks.version_unit` 结论 → 阻断
- **语义/证据/责任冲突**：与状态门/证据门/责任门复用 → 要求人工修正

## Impact

- 1 个新 spec 增量（`trust-rules` ADDED 闸门/冲突/语义 requirement）。
- 新增 `app/services/trust_rules.py`；修改 `app/api/meetings.py`、`app/api/integration.py`、`app/api/qa.py`；`Claim.status` 取值扩展（无 schema 迁移，仅字符串值）。
- 回归：平台 e2e 17 步、cross_side 5/5 需在闸门接入后仍绿（seed 数据的候选应能过闸；含「暂定」的 80℃ 候选会变待验证——符合产品语义，更新 e2e 断言）。
