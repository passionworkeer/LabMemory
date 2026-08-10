# control-tower Specification Delta

## MODIFIED Requirements

### Requirement: 研发控制塔看板
系统 SHALL 在 `GET /web/control-tower` 返回首页看板数据，包含待复核候选数、行动前阻断数、接口/证据异常数、24h 知识发布率、当前执行实验数；所有指标 MUST 标注数据来源（模拟/评测/生产），MUST NOT 伪装真实企业收益。

访问权限扩展到 pi / lead / executor / system；KPI 与 needs_action MUST 按 `accessible_project_ids` 过滤，非项目成员不可见。

#### Scenario: 看板返回 KPI
- GIVEN 平台已有种子数据
- WHEN 前端调用 `GET /web/control-tower`
- THEN 响应 SHALL 包含 `kpis`（待复核/阻断/异常/发布率/执行实验）、`needs_action`（待处理对象列表）、`anomalies`（异常队列）

#### Scenario: 执行人可访问控制塔
- GIVEN 用户 u_lin 角色为 executor 且属于项目 Alpha
- WHEN u_lin 调用 `GET /web/control-tower`
- THEN 系统 SHALL 返回 200，`needs_action` 中包含分配给 u_lin 的待审计/待启动/执行中任务与自己提交的冻结结果

## ADDED Requirements

### Requirement: 待处理对象按角色返回
系统 SHALL 在 `needs_action` 中按用户角色与归属过滤待处理对象：
- executor：`owner == user_id` 的 `needs_confirmation / approved / running / pending_audit` 任务，以及 `submitted_by_user_id == user_id` 的 `frozen` 结果
- lead / pi / system：项目内 `pending_review / ready_to_publish / needs_info` 候选、`blocked` 任务、`linked / frozen` 结果

每条 needs_action MUST 包含 `object_id`、`type`（task / candidate / result）、`problem`、`status`、`route`（前端跳转路径）。

#### Scenario: 执行人只看到自己的待办
- GIVEN 用户 u_lin（executor）属于 Alpha 项目，项目内有候选 cand_x（待复核）、任务 T001（blocked，owner=u_lin）、任务 T002（approved，owner=u_other）
- WHEN u_lin 调用 `GET /web/control-tower`
- THEN needs_action SHALL 包含 T001，MUST NOT 包含 cand_x 或 T002

#### Scenario: Lead 看到项目内全部待办
- GIVEN 用户 u_wang（lead）属于 Alpha 项目，项目内有候选 cand_x（待复核）、任务 T001（blocked）、结果 res_y（linked，待知识复核）
- WHEN u_wang 调用 `GET /web/control-tower`
- THEN needs_action SHALL 包含 cand_x、T001、res_y，每条 type 与 route 正确

#### Scenario: 异常队列仅 PI 可见
- GIVEN 用户 u_lin（executor）属于 Alpha 项目，项目内存在 failed IntegrationAction
- WHEN u_lin 调用 `GET /web/control-tower`
- THEN 响应中 `anomalies` SHALL 为空数组；MUST NOT 暴露异常详情或重试入口

### Requirement: 异常队列访问控制
系统 SHALL 限制异常队列与重试端点 `POST /web/control-tower/anomalies/{action_id}/retry` 仅 pi / system 角色可访问；其他角色调用时返回 403。`GET /web/control-tower` 中 `anomalies` 字段对非 pi / system 角色返回空数组。

#### Scenario: 异常重试
- GIVEN 异常 EVT-2098（HPLC 链接失效）状态为「待修复」，用户 u_chen 角色为 pi
- WHEN u_chen 调用 `POST /web/control-tower/anomalies/EVT-2098/retry`
- THEN 系统 SHALL 重新执行关联的 IntegrationAction，更新状态为「重试中」或「已完成」

#### Scenario: 非负责人不能重试异常
- GIVEN 用户 u_lin（executor）
- WHEN u_lin 调用 `POST /web/control-tower/anomalies/EVT-2098/retry`
- THEN 系统 SHALL 返回 403
