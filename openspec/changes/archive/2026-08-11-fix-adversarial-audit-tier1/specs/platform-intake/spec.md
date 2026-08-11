# platform-intake Specification Delta

## ADDED Requirements

### Requirement: 卡片回调不充当管理员身份
系统 SHALL 在 `/api/v1/card/callback` 解析 `open_id` → 平台 User（`feishu_user_id`）；当 `open_id` 缺失或无映射时，系统 MUST 以 `actor_id=None` 记录审计且 `AuditEvent.reason` 含原始 `open_id`，MUST NOT 回退到任何 admin 用户充当操作者。

#### Scenario: 未映射 open_id 不提权
- GIVEN 回调携带 `open_id=ou_unknown`，系统无对应 User
- WHEN 平台处理该回调
- THEN 审计记录 `actor_id` SHALL 为 None，且 MUST NOT 以 admin 身份执行

### Requirement: 卡片回调不回退已执行任务状态
系统 SHALL 在 `approve` 回调命中已 `processed` 复核时，仅当关联任务 `status ∈ {draft, needs_confirmation, blocked}` 才执行审计写；任务处于 `running`/`completed` 时 MUST NOT 改写其状态（直接返回当前结论）。同 `token` 回调 SHALL 幂等返回首次结论。

#### Scenario: 不回退 running 任务
- GIVEN 候选 cand_x 关联任务 T_x 已 `running`，复核已 processed
- WHEN 编排器转发 `approve` 回调（任意 token）
- THEN 响应 SHALL 返回当前 `{status, action_audit}` 且 T_x 状态 MUST NOT 被改写为 audited/blocked
