# platform-permissions Specification Delta

## MODIFIED Requirements

### Requirement: 角色与操作映射
系统 SHALL 按下表强制角色权限：
- executor：查看授权实验、操作行动审计、填写实际参数和结果、查看控制塔中属于自己的待处理
- lead：复核候选、操作行动审计、批准任务、处理阻断、查看控制塔
- pi：管理项目范围、审核关键版本、操作行动审计、查看控制塔（含异常队列与重试）
- algorithmic：查看预测偏差、提交模型复盘
- readonly：检索授权知识和证据

系统 SHALL 定义平台权限 `operate_action_audit`，含义为「在行动审计页面执行五类检查与修正动作」，包括触发审计、更新审计上下文、确认重审、一键修正；executor / lead / pi / system 均拥有此权限。

#### Scenario: 执行人可触发行动审计
- GIVEN 用户 u_lin 角色为 executor 且属于项目 Alpha，存在分配给 u_lin 的待审计任务 T001
- WHEN u_lin 调用 `POST /web/tasks/T001/audit`
- THEN 系统 SHALL 返回 200，并执行行动审计写入 AuditEvent

#### Scenario: 执行人可更新审计上下文
- GIVEN 用户 u_lin 角色为 executor 且任务 T001 处于 needs_confirmation
- WHEN u_lin 调用 `PUT /web/tasks/T001/audit-context`
- THEN 系统 SHALL 返回 200，更新 audit_context_json 并触发重新审计

#### Scenario: 执行人可一键修正阻断任务
- GIVEN 用户 u_lin 角色为 executor 且任务 T001 处于 blocked
- WHEN u_lin 调用 `POST /web/tasks/T001/fix`
- THEN 系统 SHALL 返回 200，创建新任务并保留旧任务为 blocked

#### Scenario: 执行人仍不能批准参数版本
- GIVEN 用户 u_lin 角色为 executor
- WHEN u_lin 调用 `POST /web/versions/{claim_id}/activate`
- THEN 系统 SHALL 返回 403，MUST NOT 修改参数版本状态

#### Scenario: 执行人仍不能复核候选
- GIVEN 用户 u_lin 角色为 executor
- WHEN u_lin 调用 `POST /web/inbox/{candidate_id}/review`
- THEN 系统 SHALL 返回 403，required_permission 为 `review_candidate`

#### Scenario: 执行人仍不能确认知识状态
- GIVEN 用户 u_lin 角色为 executor 且提交了结果 RESULT-001
- WHEN u_lin 调用 `POST /web/results/RESULT-001/review`
- THEN 系统 SHALL 返回 403，required_permission 为 `confirm_knowledge_state`

#### Scenario: 算法人员不能修改实验结论
- GIVEN 用户 u_algo 角色为 algorithmic
- WHEN u_algo 调用 `POST /web/results` 提交实验结果
- THEN 系统 SHALL 返回 403
