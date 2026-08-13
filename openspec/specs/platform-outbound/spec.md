# platform-outbound Specification

## Purpose
平台 → 飞书编排器反向联动：平台在「复核待办 / 任务启动 / 知识发布 / 审计阻断」四个业务节点，向编排器 `POST /webhook/platform` 下发 `FeishuActionRequest`（send_card / create_task / publish_doc / notify / update_base），由编排器按 `action_type` 分派到既有飞书适配器并按 `idempotency_key` 幂等；平台出站为 fire-and-forget 非阻断，`FEISHU_ORCHESTRATOR_MODE=mock` 时不真调。
## Requirements
### Requirement: 平台动作请求端点
飞书编排器 SHALL 提供 `POST /webhook/platform` 端点接收平台下发的 `FeishuActionRequest`。编排器在 mock 模式下 SHALL 仅允许本地（localhost）访问；在 real 模式下 SHALL 校验 `Authorization: Bearer {PLATFORM_API_KEY}`，失败 MUST 返回 `401` 且 MUST NOT 执行动作。

#### Scenario: real 模式缺鉴权被拒
- GIVEN 编排器以 `RUN_MODE=real` 运行且已配置 `PLATFORM_API_KEY`
- WHEN 平台以缺失或错误的 `Authorization` 头调用 `POST /webhook/platform`
- THEN 编排器 SHALL 返回 `401` 且 MUST NOT 分派动作

#### Scenario: mock 模式拒绝远端
- GIVEN 编排器以 `RUN_MODE=mock` 运行
- WHEN 来自非 localhost 地址的请求调用 `/webhook/platform`
- THEN 编排器 SHALL 返回 `403` 并提示需切 real 模式

### Requirement: 平台动作请求契约校验
编排器 SHALL 校验 `FeishuActionRequest` 的必填字段 `action_id`、`action_type`、`idempotency_key`、`actor_user_id`、`payload`；任一缺失 MUST 返回契约校验失败并 MUST NOT 执行动作。

#### Scenario: 缺少幂等键
- GIVEN 平台下发的动作请求缺少 `idempotency_key`
- WHEN 编排器校验请求
- THEN 编排器 SHALL 拒绝该请求（`ok:false`）并 MUST NOT 执行动作

### Requirement: 平台动作幂等
编排器 MUST 以 `platform_action:{idempotency_key}` 为键对平台动作做幂等判定；重复请求 SHALL 返回上次结果且 MUST NOT 重复执行下游飞书动作。

#### Scenario: 重复下发知识文档
- GIVEN 同一 `idempotency_key` 的 `publish_doc` 动作已成功处理
- WHEN 平台重发相同 `idempotency_key`
- THEN 编排器 SHALL 返回缓存结果且 MUST NOT 重复发布文档

### Requirement: 平台动作分派
编排器 SHALL 按 `action_type` 分派 `FeishuActionRequest` 到既有飞书适配器：`send_card` → 交互卡片、`create_task` → 飞书任务（成功后回写平台 `feishu_task_guid`）、`publish_doc` → 知识文档、`notify` → 告警卡片、`update_base` → 多维表格台账。未知 `action_type` MUST 明确失败。

#### Scenario: 创建任务并回写
- GIVEN `create_task` 动作携带候选信息与 `candidate_id`
- WHEN 编排器分派该动作
- THEN 编排器 SHALL 创建飞书任务并调用平台 `POST /api/v1/task/status` 回写 `feishu_task_guid` 与 `success`

#### Scenario: 未知动作类型失败
- GIVEN 动作请求 `action_type` 为未支持值
- WHEN 编排器分派
- THEN 编排器 SHALL 返回 `ok:false` 并记录失败，MUST NOT 静默成功

### Requirement: 平台出站触发点
平台 SHALL 在以下业务节点主动向编排器下发 `FeishuActionRequest`（均非阻断，失败不影响主业务）：
- 新候选待复核 → `send_card`（单次 ≤3 张）
- 任务启动 → `create_task`
- 知识发布 → `publish_doc`
- 行动前审计阻断 → `notify`

#### Scenario: 复核待办下发卡片
- GIVEN 平台通过 `/api/v1/candidates` 收到含 `needs_review` 候选的候选包
- WHEN 候选受理完成
- THEN 平台 SHALL 请求编排器下发复核卡片（≤3 张）

#### Scenario: 审计阻断下发通知
- GIVEN 某任务行动前审计结论为 `blocked`
- WHEN 平台完成审计落库
- THEN 平台 SHALL 请求编排器下发告警/阻断通知

### Requirement: 平台出站非阻断与模式隔离
平台出站调用 SHALL 为 fire-and-forget：超时或失败 MUST 只记录日志，MUST NOT 改变主接口响应或状态机。当 `FEISHU_ORCHESTRATOR_MODE != "real"` 时，平台 MUST NOT 发起真实 HTTP 调用（记日志并跳过）。

#### Scenario: mock 模式不真调
- GIVEN 平台配置 `FEISHU_ORCHESTRATOR_MODE=mock`
- WHEN 业务节点触发反向联动
- THEN 平台 SHALL 记录跳过日志且不发起对编排器的 HTTP 调用

#### Scenario: 编排器不可达不阻断主业务
- GIVEN 平台 `FEISHU_ORCHESTRATOR_MODE=real` 但编排器不可达
- WHEN 业务节点触发反向联动
- THEN 平台 SHALL 记录失败日志并继续返回主业务结果，MUST NOT 抛错中断

### Requirement: 知识文档类型映射
平台在 `publish_doc` 触发时 SHALL 按结果 `knowledge_status` 映射文档类型：`supported` → `success`、`refuted` → `failure`、`partially_supported` → `failure`（失败边界根因 MUST 标记为「假设」）。其他状态 SHALL 映射为 `pending`。

#### Scenario: 部分支持发布失败边界文档
- GIVEN 平台判定某结果为 `partially_supported` 并发布为知识
- WHEN 平台下发 `publish_doc`
- THEN 平台 SHALL 以 `doc_type=failure` 下发，且编排器发布的失败边界文档根因 SHALL 标记「假设」

