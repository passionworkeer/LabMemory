# experiment-passport Specification Delta

## MODIFIED Requirements

### Requirement: 实验护照时间线
系统 SHALL 在 `GET /web/passport/{experiment_ref}` 返回以实验为中心的统一时间线，按时间排序聚合会议决策、参数版本、任务、实际执行、结果、异常、知识状态更新，以及所有正式状态变更的 AuditEvent 操作记录。

每条 timeline 条目 SHALL 含 `time`、`object_type`、`object_id`、`event`、`planned_or_actual`、`parameter_version`、`evidence_source`、`trust_status`、`owner`、`affected_objects`。

对 `object_type=audit_event` 的条目，系统 SHALL 额外返回 `action`、`target_type`、`target_id`、`before_state`、`after_state`、`details`、`reason` 字段，使前端能展示操作动作、操作者、前后状态与变更详情。

#### Scenario: 护照聚合多对象
- GIVEN 实验 EXP-SYN-0042 关联了会议、决策、任务、结果、失败卡
- WHEN 前端调用 `GET /web/passport/EXP-SYN-0042`
- THEN 响应 SHALL 返回 `timeline[]`，包含上述对象与 AuditEvent 条目，按时间排序

#### Scenario: 护照时间线包含行动审计操作
- GIVEN 任务 T001（属于实验 EXP-AUDIT-001）经历了 action_audit_executed（结果=blocked）与 task_one_click_fix（创建 T002）
- WHEN 前端调用 `GET /web/passport/EXP-AUDIT-001`
- THEN timeline SHALL 包含两条 `object_type=audit_event` 条目，action 分别为 `action_audit_executed` 与 `task_one_click_fix`，每条含 actor、before_state、after_state、details

#### Scenario: 护照时间线包含审计上下文更新
- GIVEN 任务 T001 处于 needs_confirmation，负责人填写物料/设备后触发 task_audit_context_updated
- WHEN 前端调用 `GET /web/passport/EXP-AUDIT-001`
- THEN timeline SHALL 包含 `object_type=audit_event`、`action=task_audit_context_updated` 的条目，details 含 before/after 上下文对比

#### Scenario: 护照时间线包含结果复核操作
- GIVEN 结果 RESULT-001 经历 result_submitted、frozen_result_resolved、result_reviewed_and_published
- WHEN 前端调用 `GET /web/passport/EXP-RESULT-001`
- THEN timeline SHALL 按时间顺序包含上述三条 AuditEvent 条目，每条 actor、before_state、after_state、details 完整

### Requirement: 双向证据关系
系统 SHALL 支持从结果回看会议原话，也支持从决策查看受影响任务、文档和后续结果。

#### Scenario: 从结果回看决策
- GIVEN 结果 RESULT-0042 关联任务 TASK-1001
- WHEN 系统构建护照关系图
- THEN 系统 SHALL 返回 `relations` 包含 `from_result_to_decision`（RESULT -> 参数版本 -> DECISION -> 会议原话）与 `from_decision_to_impact`（DECISION -> TASK -> RESULT -> FAIL）

### Requirement: 历史版本保留
参数区域 SHALL 显示当前有效值、历史版本、替代原因、支持证据、适用范围；历史版本永久保留，不静默覆盖；过期版本明确标识但仍可追溯。

#### Scenario: 切换历史版本
- GIVEN 参数「推荐温度」有 v1(80℃) 和 v2(70℃)
- WHEN 用户在护照中切换到 v1
- THEN 系统 SHALL 展示 v1 的值、状态（已过期）、替代原因、被 v2 替代的时间，MUST NOT 删除 v1 数据
