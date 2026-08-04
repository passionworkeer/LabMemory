# Contracts Specification

## Purpose
定义飞书编排子系统（feishu-orchestrator）与自研平台子系统（labmemory-platform）之间的冻结接口契约，使两侧可各自用 Mock 并行开发、独立验收。

## Requirements

### Requirement: MeetingPackage（飞书侧 → 平台）
飞书侧 SHALL 向平台提交 `MeetingPackage`，至少包含：`schema_version`、`source`、`meeting_id`、`minute_token`、`experiment_hint`、`title`、`participants[]`（user_id/name）、`segments[]`（segment_id/speaker/start_ms/text）、`source_url`、`occurred_at`。

#### Scenario: 真实妙记接入
- GIVEN 妙记生成事件到达
- WHEN 飞书侧读取逐字稿并组装包
- THEN 系统 SHALL 通过 `POST /integration/meetings` 提交标准包，缺失字段显式置空不得伪造

### Requirement: CandidatePackage（Aily → 平台）
Aily 编译结果 SHALL 以 `CandidatePackage` 提交，至少包含：`schema_version`、`compiler_version`、`meeting_id`、`candidates[]`（type/name/value/unit/semantic/status_hint/scope/evidence/confidence）。

#### Requirement: FeishuActionRequest（平台 → 飞书侧）
平台 SHALL 通过 `FeishuActionRequest` 请求飞书动作，包含 `action_id`、`action_type`、`idempotency_key`、`actor_user_id`、`payload`；系统 MUST 仅在平台返回 approved 且 audit=pass 后发起创建飞书任务。

#### Scenario: 仅审核通过后建任务
- GIVEN 平台决策收件箱已确认且行动前审计为通过
- WHEN 平台请求飞书侧创建任务
- THEN 系统 SHALL 创建飞书任务并回写 `feishu_task_guid` 至平台

### Requirement: CardCallback（飞书卡片 → 平台）
飞书交互卡片按钮回调 SHALL 经验签后转发平台审核接口（如确认 / 修正 / 驳回 / 一键替换当前版本）。

### Requirement: 契约冻结与版本化
接口契约字段一旦冻结，两侧各自使用 Mock 并行开发；任何修改 MUST 经版本号升级并记录在共享 `contracts/` 目录。
