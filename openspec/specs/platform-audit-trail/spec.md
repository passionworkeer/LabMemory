# platform-audit-trail Specification

## Purpose
TBD - created by archiving change add-labmemory-platform-implementation. Update Purpose after archive.
## Requirements
### Requirement: AuditEvent 通用模型
系统 SHALL 用单一 `AuditEvent` 表覆盖所有正式状态变更，字段包含 `event_id`、`actor_user_id`、`action`、`target_type`、`target_id`、`before_state`、`after_state`、`details_json`、`ip_address`、`user_agent`、`created_at`。

#### Scenario: 候选确认写入审计
- GIVEN 负责人确认候选 CAND-001 为「待验证」
- WHEN 系统更新候选状态
- THEN 系统 SHALL 写入 AuditEvent，`target_type=candidate`、`target_id=CAND-001`、`before_state=pending_review`、`after_state=pending_review`（语义修正不改状态但留痕）、`details_json` 含三值字段

### Requirement: 覆盖范围
AuditEvent MUST 覆盖以下对象的状态变更：候选、主张、参数版本、决策、任务、结果、知识卡、失败边界、集成动作；非状态变更的查询操作 MUST NOT 写入审计。

#### Scenario: 任务一键修正留痕
- GIVEN 任务 T001 被阻断，负责人调用一键修正
- WHEN 系统创建 T002 并标记 T001 为 blocked
- THEN 系统 SHALL 写入至少 3 条 AuditEvent：T001 status->blocked、T002 created、TaskRevision created

### Requirement: 不可篡改
AuditEvent 写入后 MUST NOT 被修改或删除；仅可通过新增 AuditEvent 修正前序记录。

#### Scenario: 禁止删除审计
- GIVEN 任意 AuditEvent 已写入
- WHEN 任何 API 调用尝试删除或更新该事件
- THEN 系统 SHALL 拒绝（无对应端点），MUST NOT 提供 delete/update audit event 接口

### Requirement: 审计可追溯
系统 SHALL 支持按 `target_type` + `target_id` 查询完整审计轨迹，按时间倒序返回。

#### Scenario: 查询任务审计历史
- GIVEN 任务 T001 经历创建、阻断、一键修正
- WHEN 前端调用 `GET /web/tasks/T001/audit`
- THEN 响应 SHALL 返回该任务所有 AuditEvent，含操作者、时间、前后状态、原因

