# experiment-passport Specification

## ADDED Requirements

### Requirement: 实验护照时间线
系统 SHALL 在 `GET /web/passport/{experiment_ref}` 返回以实验为中心的统一时间线，按时间排序聚合会议决策、参数版本、任务、实际执行、结果、异常、知识状态更新。

#### Scenario: 护照聚合多对象
- GIVEN 实验 EXP-SYN-0042 关联了会议、决策、任务、结果、失败卡
- WHEN 前端调用 `GET /web/passport/EXP-SYN-0042`
- THEN 响应 SHALL 返回 `timeline[]`，每条含 `time`、`object_type`、`object_id`、`event`、`planned_or_actual`、`parameter_version`、`evidence_source`、`trust_status`、`owner`、`affected_objects`

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
