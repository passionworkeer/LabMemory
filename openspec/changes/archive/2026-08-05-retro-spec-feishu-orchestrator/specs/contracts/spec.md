# contracts 规格增量

## MODIFIED Requirements

### Requirement: MeetingPackage（飞书侧 → 平台）
飞书侧 SHALL 向平台提交 `MeetingPackage`，字段以 `contracts/meeting-package.schema.json` 为准，必填：`schema_version`、`source`、`source_object_id`、`title`、`content`、`source_url`、`captured_at`；`content.transcript[]` 每个片段必填 `speaker`、`start_offset_sec`、`end_offset_sec`、`text`。缺失字段 MUST 显式置空，MUST NOT 伪造。

#### Scenario: 真实妙记接入
- GIVEN 妙记生成事件到达
- WHEN 飞书侧读取逐字稿并组装包
- THEN 系统 SHALL 提交符合 `meeting-package.schema.json` 的标准包，`source_object_id` 取妙记对象标识，`captured_at` 记录采集时间

#### Scenario: 逐字稿缺失
- GIVEN 妙记详情不含逐字稿
- WHEN 飞书侧组装 `MeetingPackage`
- THEN `content.transcript` SHALL 为空数组且不提交编译，MUST NOT 用摘要文本填充

### Requirement: CandidatePackage（Aily → 平台）
Aily 编译结果 SHALL 以 `CandidatePackage` 提交，字段以 `contracts/candidate-package.schema.json` 为准，必填：`schema_version`、`source_package_id`、`aily_skill_version`、`candidates[]`；每个候选必填 `candidate_id`、`type`、`title`、`confidence`、`evidence`、`status`。`source_package_id` MUST 可回溯到对应 `MeetingPackage`，`aily_skill_version` MUST 记录编译技能版本以便复现。

#### Scenario: 编译结果可回溯
- GIVEN 平台收到一份 `CandidatePackage`
- WHEN 平台需要复核某候选的来源
- THEN 平台 SHALL 能通过 `source_package_id` 定位原会议包，并通过 `aily_skill_version` 确定编译版本

### Requirement: FeishuActionRequest（平台 → 飞书侧）
平台 SHALL 通过 `FeishuActionRequest` 请求飞书动作；`contracts/feishu-action-request.schema.json` 必填字段 MUST 包含 `action_id`、`action_type`、`idempotency_key`、`actor_user_id`、`payload`。系统 MUST 仅在平台返回 `status=approved` 且 `action_audit=pass` 后发起创建飞书任务。

#### Scenario: 仅审核通过后建任务
- GIVEN 平台决策收件箱已确认且行动前审计为通过
- WHEN 平台请求飞书侧创建任务
- THEN 系统 SHALL 创建飞书任务并回写 `feishu_task_guid` 至平台

#### Scenario: 缺少幂等键
- GIVEN 平台下发的动作请求缺少 `idempotency_key` 或 `actor_user_id`
- WHEN 飞书侧校验请求
- THEN 系统 SHALL 拒绝该请求并返回契约校验失败，MUST NOT 执行动作

### Requirement: CardCallback（飞书卡片 → 平台）
飞书交互卡片按钮回调 SHALL 经验签后转发平台审核接口（如确认 / 修正 / 驳回 / 一键替换当前版本）。转发目标为 `POST {PLATFORM_API_BASE}/v1/card/callback`；平台响应 SHALL 包含 `status` 与 `action_audit`，飞书侧按此分流，MUST NOT 自行判定审核结论。

#### Scenario: 回调转发与分流
- GIVEN 复核人点击卡片按钮
- WHEN 飞书侧验签通过并转发平台
- THEN 飞书侧 SHALL 按平台返回的 `status`（`approved` / `rejected` / `blocked`）与 `action_audit` 执行对应后续动作

### Requirement: 契约冻结与版本化
接口契约字段一旦冻结，两侧各自使用 Mock 并行开发；任何修改 MUST 经版本号升级并记录在共享 `contracts/` 目录。

#### Scenario: 必填字段变更
- GIVEN 某契约需要新增或调整必填字段
- WHEN 任一侧提出该修改
- THEN 修改 MUST 先经 OpenSpec change 批准，`schema_version` MUST 升级，且两侧 Mock 与样例数据 SHALL 同步更新

## ADDED Requirements

### Requirement: 平台集成接口路径
飞书侧与平台之间的集成接口 SHALL 以 `PLATFORM_API_BASE` 为基址（默认 `https://labmemory.example.com/api`），路径固定为：`POST /v1/candidates`（提交候选包）、`POST /v1/card/callback`（转发卡片回调）、`POST /v1/task/status`（回写任务状态）、`GET /v1/candidates/{candidate_id}`（查询候选详情）。所有请求 MUST 携带 `Authorization: Bearer {PLATFORM_API_KEY}`。

#### Scenario: 提交候选包
- GIVEN Aily 编译完成
- WHEN 飞书侧提交候选
- THEN 系统 SHALL 调用 `POST /v1/candidates` 并携带鉴权头，平台 SHALL 返回每个候选的受理状态与待复核数量

#### Scenario: 回写任务状态
- GIVEN 飞书任务创建完成或失败
- WHEN 飞书侧回写平台
- THEN 系统 SHALL 调用 `POST /v1/task/status` 提交 `candidate_id`、`feishu_task_guid` 与 `pending` / `success` / `failed` 之一

#### Scenario: 路径变更需走 change
- GIVEN 需要调整任一集成接口路径或鉴权方式
- WHEN 任一侧提出变更
- THEN 变更 MUST 先经 OpenSpec change 与契约版本号升级，MUST NOT 直接改代码后再补文档
