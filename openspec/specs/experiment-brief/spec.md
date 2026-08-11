# experiment-brief Specification

## Purpose
TBD - created by archiving change add-experiment-brief-and-decision-qa-specs. Update Purpose after archive.
## Requirements
### Requirement: 简报访问权限
系统 SHALL 校验请求者对实验简报的访问权限：`admin` / `pi` 角色可访问任意实验；其他角色 MUST 为该实验的成员，否则返回无权错误。

#### Scenario: 非成员访问简报
- GIVEN 用户 u_web 角色为 executor 且非实验 EXP-001 的成员
- WHEN u_web 请求 `GET /api/experiments/EXP-001/brief`
- THEN 系统 SHALL 拒绝访问并返回无权限错误

#### Scenario: admin 访问任意实验简报
- GIVEN 用户 u_admin 角色为 admin，且不属于实验 EXP-002
- WHEN u_admin 请求 `GET /api/experiments/EXP-002/brief`
- THEN 系统 SHALL 返回该实验的完整简报

### Requirement: 简报组装当前主张
系统 SHALL 从该实验 `current` 状态的最新主张组装 `current_claim`，并携带其会议 ID、实验 ID 与参数版本信息；实验不存在时 SHALL 返回明确错误。

#### Scenario: 实验不存在
- GIVEN 请求的实验 ID 在系统中不存在
- WHEN 用户请求该实验的简报
- THEN 系统 SHALL 返回「实验不存在」错误

#### Scenario: 存在当前主张
- GIVEN 实验 EXP-001 存在一条 `current` 主张 C003（含参数版本 v2）
- WHEN 用户请求 EXP-001 的简报
- THEN 简报中的 `current_claim` SHALL 指向 C003 且包含 `meeting_id`、`experiment_id` 与 `parameter_version`

#### Scenario: 无当前主张
- GIVEN 实验 EXP-001 没有任何 `current` 状态主张
- WHEN 用户请求 EXP-001 的简报
- THEN `current_claim` SHALL 为 `null`

### Requirement: 简报组装上一轮结果
系统 SHALL 取该实验最近一条 `published` 状态结果组装 `last_result`，并附带其任务 ID 与计划参数。

#### Scenario: 存在已发布结果
- GIVEN 实验 EXP-001 存在两条 `published` 结果，其中 R102 的 `published_at` 更新
- WHEN 用户请求 EXP-001 的简报
- THEN `last_result` SHALL 指向 R102 并包含 `task_id` 与 `planned_params`

### Requirement: 简报聚合失败边界
系统 SHALL 聚合该实验全部已发布结果中非空的 `failure_boundary`，按列表返回于 `failure_boundaries`。

#### Scenario: 多条失败边界聚合
- GIVEN 实验 EXP-001 的两条已发布结果分别携带失败边界「温度超限」与「催化剂批次差异」
- WHEN 用户请求 EXP-001 的简报
- THEN `failure_boundaries` SHALL 为包含「温度超限」与「催化剂批次差异」两项的数组

### Requirement: 简报提供当前目标
系统 SHALL 以该实验最近一次会议的 `summary` 作为 `current_goal`；无会议记录时返回 `null`。

#### Scenario: 无会议记录
- GIVEN 实验 EXP-001 尚无任何会议
- WHEN 用户请求 EXP-001 的简报
- THEN `current_goal` SHALL 为 `null`

### Requirement: 简报响应结构
系统 SHALL 返回固定结构的简报响应，字段至少包含 `experiment_id`、`name`、`status`、`current_goal`、`current_claim`、`last_result`、`failure_boundaries`、`resources`、`pending_questions`。

#### Scenario: 完整简报结构
- GIVEN 用户对实验 EXP-001 拥有访问权限
- WHEN 用户请求 EXP-001 的简报
- THEN 响应 SHALL 包含以上全部字段且类型与定义一致

