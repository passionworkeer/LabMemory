# action-audit Specification Delta

## ADDED Requirements

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
