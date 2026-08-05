# feishu-actions 规格增量

## ADDED Requirements

### Requirement: 复核卡片下发
系统 SHALL 在候选提交平台成功后，向指定复核人下发交互卡片；单次编排下发卡片数量 SHALL 有上限（当前为 3 张），超出部分 SHALL 引导至平台决策收件箱处理，MUST NOT 无限量刷卡片。

#### Scenario: 下发复核卡片
- GIVEN 平台提交成功且提供了 `reviewer_id`
- WHEN 系统下发复核卡片
- THEN 卡片 SHALL 展示候选标题、类型、原文证据与置信度，编排状态 SHALL 迁移为 `reviewing`

#### Scenario: 候选数量超过卡片上限
- GIVEN 一次编译产出 12 个候选
- WHEN 系统下发复核卡片
- THEN 系统 SHALL 只下发前 3 张卡片并在卡片中给出收件箱入口，MUST NOT 逐条轰炸复核人

### Requirement: 卡片回调三值分流
系统 SHALL 把卡片按钮回调转发平台审核接口，并严格按平台返回结果分流为三种结局：`approved` 且 `action_audit=pass` → 通过；`rejected` → 驳回；`blocked` → 阻断。飞书侧 MUST NOT 自行判定审核结论。

#### Scenario: 通过并创建任务
- GIVEN 平台返回 `status=approved` 且 `action_audit=pass`
- WHEN 系统处理回调
- THEN 系统 SHALL 依次：置状态 `approved` → 创建飞书任务 → 回写 `feishu_task_guid` 与 `success` → 置状态 `completed` → 下发通过卡片

#### Scenario: 驳回
- GIVEN 平台返回 `status=rejected`
- WHEN 系统处理回调
- THEN 系统 SHALL 将状态置为 `failed` 并记录原因为驳回，MUST NOT 创建飞书任务

#### Scenario: 审计阻断
- GIVEN 平台返回 `status=blocked`
- WHEN 系统处理回调
- THEN 系统 SHALL 将状态置为 `blocked`、下发含证据包与一键修正入口的阻断卡片，且 MUST NOT 调用飞书任务创建接口

#### Scenario: approved 但审计未通过
- GIVEN 平台返回 `status=approved` 但 `action_audit` 不为 `pass`
- WHEN 系统处理回调
- THEN 系统 MUST NOT 创建飞书任务，SHALL 按需确认 / 阻断路径处理

### Requirement: 卡片回调幂等
系统 MUST 以 `card_callback:{callback_token}` 为键对卡片回调做幂等判定；重复点击同一按钮 SHALL 只产生一次下游动作。

#### Scenario: 复核人连点通过按钮
- GIVEN 同一 `callback_token` 的回调已被成功处理
- WHEN 复核人再次点击同一按钮
- THEN 系统 SHALL 返回上次结果，MUST NOT 重复创建飞书任务

### Requirement: 任务创建与结果回写
系统 SHALL 由候选对象生成飞书任务，并把 `feishu_task_guid` 与执行状态（`pending` / `success` / `failed`）回写平台。任务创建失败时 MUST 回写 `failed` 与错误信息，MUST NOT 静默丢弃。

#### Scenario: 任务创建失败
- GIVEN 飞书任务创建接口返回错误
- WHEN 系统处理通过回调
- THEN 系统 SHALL 向平台回写 `status=failed` 与错误详情，并保留候选可重试

### Requirement: 协同看板回流
系统 SHALL 把候选与任务的关键字段写入飞书多维表格作为协同看板，并在状态变化时更新对应记录与任务链接，MUST NOT 以新增记录替代状态更新造成重复行。

#### Scenario: 候选状态变化更新看板
- GIVEN 某候选已在多维表格中存在记录
- WHEN 该候选状态由候选变为已批准
- THEN 系统 SHALL 更新原记录状态与任务链接，MUST NOT 追加一条新记录

### Requirement: 知识文档回流
系统 SHALL 把平台判定的知识结果发布为飞书云文档，并按结果性质区分成功案例、失败边界案例、待验证案例三种形态；失败边界文档中的根因 MUST 显式标记为「假设」。

#### Scenario: 部分支持的结果
- GIVEN 平台判定某结果为「部分支持」并生成失败边界卡
- WHEN 系统发布知识文档
- THEN 系统 SHALL 发布失败边界案例文档，其中根因段落 SHALL 标记为「假设」，MUST NOT 表述为已证实事实

### Requirement: 异常告警卡片
系统 SHALL 在编排失败、重试耗尽或状态长时间停滞时下发告警卡片，卡片 SHALL 包含失败阶段、对象 ID 与可执行的重放入口。

#### Scenario: 重试耗尽
- GIVEN 某外部调用重试达到 `MAX_RETRIES` 仍失败
- WHEN 系统结束该次编排
- THEN 系统 SHALL 下发告警卡片并把编排状态置为 `failed`
