# Action Audit Specification

## Purpose
在实验任务进入执行前，校验参数版本、单位、证据、审批、资源与失败边界，给出可解释、可修正的审计结论，确保错误知识在进入实验前被阻断。
## Requirements
### Requirement: 五类检查
系统 SHALL 在任务申请执行前，对以下五类检查项依次校验：版本与单位、证据与范围、审批状态、物料设备与排期、失败边界与争议。

#### Scenario: 五类检查全部通过
- GIVEN 任务引用的参数版本为当前 active 且范围匹配、证据有效、已审批、资源满足、无未解决冲突
- WHEN 系统执行行动前审计
- THEN 审计结果 SHALL 为 `通过`，并记录证据包与审计时间

### Requirement: 审计三态结论
系统 MUST 对每个任务的行动前审计返回 `通过` / `需确认` / `阻断` 三者之一，且每项必须附带原因与建议动作。

#### Scenario: 中风险问题
- GIVEN 审计发现证据不足或设备排期冲突等中风险问题
- WHEN 系统执行行动前审计
- THEN 审计结果 SHALL 为 `需确认`，任务保持草稿或待审核，并通知负责人补充或确认

#### Scenario: 高风险问题
- GIVEN 审计发现旧版本引用、范围不匹配或未授权审批
- WHEN 系统执行行动前审计
- THEN 审计结果 SHALL 为 `阻断`，严重程度标记为「高」

### Requirement: 旧参数版本阻断
系统 MUST 在任务引用的参数版本非当前 active、或已被 `superseded` 且适用范围一致时，返回 `阻断`，并返回新版本、支持证据、替代原因、受影响对象与建议修正动作。

#### Scenario: 引用已被替代的旧版本
- GIVEN 任务计划温度为 80℃（v1, C001），当前有效主张为 70℃ v2（C003，replaces C001），且两者适用范围均为 S1/0.20 mol/L/2h/催化剂 B
- WHEN 该任务申请执行行动前审计
- THEN 审计结果 SHALL 为 `阻断`，返回证据包（两组复现实验 EXP-0707-04=78%、EXP-0707-05=72%）、影响对象与建议修正 `replace_with_current_version`

### Requirement: 阻断不创建正式任务
系统 MUST NOT 在审计结果为 `阻断` 时请求飞书创建正式执行任务。

#### Scenario: 阻断后保留旧任务
- GIVEN 任务 T001 审计结果为 `阻断`
- WHEN 系统尝试推进任务
- THEN 系统 SHALL 不调用飞书任务创建接口，并将 T001 保留为 `已阻断` 状态

### Requirement: 一键修正生成新版本任务
系统 SHALL 提供「一键修正为当前版本」动作；修正 MUST 生成新的 task_revision，保留旧任务草稿与操作人，不静默覆盖原任务内容。

#### Scenario: 负责人确认一键改为当前版本
- GIVEN 任务 T001（80℃）被阻断，展示 70℃ v2 证据
- WHEN 负责人确认一键修正为 70℃
- THEN 系统 SHALL 生成新任务 T002（70℃）且审计通过，旧 T001 保留为 `已阻断`，并创建飞书任务

### Requirement: 行动审计操作权限
系统 SHALL 对行动审计的四个写操作端点统一要求平台权限 `operate_action_audit`：`POST /web/tasks/{task_id}/audit`（触发审计）、`PUT /web/tasks/{task_id}/audit-context`（更新审计上下文）、`POST /web/tasks/{task_id}/confirm`（确认重审）、`POST /web/tasks/{task_id}/fix`（一键修正）。`GET /web/tasks/{task_id}/audit` 与 `GET /web/tasks` 仅需 `view_experiment`。

executor / lead / pi / system 均拥有 `operate_action_audit` 权限，使执行人能在 lead 不在场时独立完成行动审计闭环。

#### Scenario: 执行人触发审计
- GIVEN 用户 u_lin 角色为 executor 且任务 T001 属于其项目
- WHEN u_lin 调用 `POST /web/tasks/T001/audit`
- THEN 系统 SHALL 返回 200，返回 AuditOutcome，并写入 AuditEvent（action=action_audit_executed）

#### Scenario: 执行人更新审计上下文后重新审计
- GIVEN 用户 u_lin 角色为 executor 且任务 T001 状态为 needs_confirmation
- WHEN u_lin 调用 `PUT /web/tasks/T001/audit-context` 提供 resources_available=true、equipment_available=true
- THEN 系统 SHALL 返回 200，task.status 改为 pending_audit，并写入 AuditEvent（action=task_audit_context_updated）

#### Scenario: 执行人一键修正阻断任务
- GIVEN 用户 u_lin 角色为 executor 且任务 T001 状态为 blocked，存在同 claim 当前 active 版本
- WHEN u_lin 调用 `POST /web/tasks/T001/fix`
- THEN 系统 SHALL 返回 200，创建新任务并保留旧 T001 为 blocked，写入 AuditEvent（action=task_one_click_fix）

#### Scenario: 执行人确认重审
- GIVEN 用户 u_lin 角色为 executor 且任务 T001 状态为 needs_confirmation
- WHEN u_lin 调用 `POST /web/tasks/T001/confirm`
- THEN 系统 SHALL 返回 200，task.status 改为 pending_audit 后立即重新执行审计，写入 AuditEvent（action=task_confirmed_for_reaudit）

#### Scenario: 只读成员不能触发审计
- GIVEN 用户 u_guest 角色为 readonly
- WHEN u_guest 调用 `POST /web/tasks/T001/audit`
- THEN 系统 SHALL 返回 403，required_permission 为 `operate_action_audit`

