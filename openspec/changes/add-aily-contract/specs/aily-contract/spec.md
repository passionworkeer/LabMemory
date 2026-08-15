# aily-contract Specification Delta

## ADDED Requirements

### Requirement: 入站接口鉴权与路径
平台 SHALL 在 `/v1/*` 前缀下暴露 Aily 集成接口，并复用 `verify_platform_api_key` 鉴权（接受 `Authorization: Bearer {PLATFORM_API_KEY}`，兼容 `X-Platform-Api-Key`）。鉴权失败 MUST 返回 `403` 且 MUST NOT 处理请求。

#### Scenario: Bearer 通过
- GIVEN Aily 以 `Authorization: Bearer {PLATFORM_API_KEY}` 调用 `POST /v1/transcripts`
- WHEN 平台校验鉴权
- THEN 系统 SHALL 通过并处理请求

#### Scenario: 缺鉴权被拒
- GIVEN 请求未携带有效鉴权头
- WHEN 平台校验鉴权
- THEN 系统 SHALL 返回 `403`

### Requirement: 逐字稿接入
平台 SHALL 提供 `POST /v1/transcripts` 接收妙记/逐字稿（`meeting_id`、`note_id`、`speakers[]`、`segments[]`），创建会议与待复核项并返回 `transcript_id`。请求 SHALL 可携带 `experiment_id`（缺失回退 `EXP-DEMO-001`）。

#### Scenario: 接收逐字稿
- GIVEN 请求含 `meeting_id` 与 `segments[]`
- WHEN 平台处理
- THEN 系统 SHALL 创建会议（含逐字稿）与 pending 复核，并返回 `transcript_id`（等于 `meeting_id`）

### Requirement: 抽取结果回写
平台 SHALL 提供 `POST /v1/extractions` 接收 Aily 抽取结果（`transcript_id`、`params[]`、`disputes[]`、`risks[]`、`task_candidates[]`），保存候选并返回 `extraction_id` 与各项内部 ID。

#### Scenario: 回写抽取
- GIVEN `transcript_id` 已存在
- WHEN Aily 回写抽取结果
- THEN 系统 SHALL 保存候选包并返回 `extraction_id` 及各候选 `candidate_id`

### Requirement: 决策项创建与裁决
平台 SHALL 提供 `POST /v1/decision-inbox`（创建待复核项，返回 `decision_id`）与 `POST /v1/decision-inbox/{id}/verdict`（`pass`/`reject` + `reviewer` + `comment` + `verdict_at`，返回 `ack`）。`pass` MUST 走六道闸门审计，未过 MUST NOT 乐观放行。

#### Scenario: pass 通过闸门
- GIVEN 决策项关联候选满足六道闸门
- WHEN Aily 提交 `verdict=pass`
- THEN 系统 SHALL 生成主张与任务草稿并返回 `ack`

#### Scenario: pass 未过闸门诚实阻断
- GIVEN 决策项候选未过闸门
- WHEN Aily 提交 `verdict=pass`
- THEN 系统 SHALL 返回阻断结果而非乐观 pass

### Requirement: 参数版本签发
平台 SHALL 提供 `POST /v1/parameter-versions` 签发正式参数版本（`decision_id`、`params[]`、`effective_from`、`evidence_refs[]`），返回 `version_id`（对应平台主张 ID）。

#### Scenario: 签发版本
- GIVEN 决策项已存在
- WHEN 平台签发参数版本
- THEN 系统 SHALL 生成 current 主张（旧主张 supersede）并返回 `version_id`

### Requirement: 执行前自检与执行回写
平台 SHALL 提供 `POST /v1/preflight`（`version_id`、`executor`、`planned_at` → `verdict(ok/block)`、`reasons[]`、`boundary_check{}`）与 `POST /v1/executions`（`version_id`、`actual_params{}`、`results{}`、`executor`、`executed_at` → `execution_id`）。

#### Scenario: 自检阻断
- GIVEN 版本对应任务引用旧版本或资源未就绪
- WHEN 平台执行自检
- THEN 系统 SHALL 返回 `verdict=block` 与 `reasons[]`

#### Scenario: 执行结果偏差
- GIVEN `actual_params` 与计划参数 key 不一致
- WHEN 平台回写执行结果
- THEN 系统 SHALL 记录 frozen（偏差）并返回 `execution_id`

### Requirement: 护照更新与知识发布
平台 SHALL 提供 `PATCH /v1/passports/{passport_id}`（更新 `status` / `failure_boundary{}` / `claim_state`）与 `POST /v1/knowledge`（`passport_id`、`title`、`summary`、`doc_refs[]` → `knowledge_id`）。

#### Scenario: 发布知识
- GIVEN 护照对应结果已提交
- WHEN 平台发布知识
- THEN 系统 SHALL 更新知识状态并返回 `knowledge_id`

### Requirement: 复验任务
平台 SHALL 提供 `POST /v1/reverify-tasks`（`passport_id`、`assignee`、`due_at`、`criteria[]` → `reverify_id`）创建复验任务。

#### Scenario: 创建复验
- GIVEN 护照存在
- WHEN 平台创建复验任务
- THEN 系统 SHALL 生成任务并返回 `reverify_id`

### Requirement: 出站 webhook 签名与幂等
平台 SHALL 以 HMAC-SHA256 签名头（`X-LabMemory-Signature`，`sha256(secret + timestamp + nonce + body)`）并携带幂等键（`X-LabMemory-Idempotency-Key`）推送 5 类事件（decision.pending / preflight.blocked / execution.deviated / knowledge.ready / reverify.due）。`AILY_INTEGRATION_ENABLED != "true"` 时 MUST NOT 真实推送。

#### Scenario: 事件带签名与幂等键
- GIVEN 业务触发出站事件
- WHEN 平台推送
- THEN 请求 SHALL 含签名头与幂等键，Aily 侧可去重

#### Scenario: 未启用不真调
- GIVEN `AILY_INTEGRATION_ENABLED` 非 `true`
- WHEN 业务触发出站事件
- THEN 平台 SHALL 记录跳过且不发起 HTTP 调用
