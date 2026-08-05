# orchestration-reliability 规格增量

## ADDED Requirements

### Requirement: 编排状态机
系统 SHALL 为每个编排对象维护状态，取值限定为：`waiting_minutes`、`minutes_ready`、`compiling`、`submitted`、`reviewing`、`approved`、`completed`、`blocked`、`failed`。状态变更 MUST 追加历史记录（`from` / `to` / `timestamp`），MUST NOT 覆盖历史。

#### Scenario: 状态迁移留痕
- GIVEN 某对象状态由 `compiling` 迁移为 `submitted`
- WHEN 系统写入新状态
- THEN 系统 SHALL 在该对象历史中追加一条含来源状态、目标状态与时间戳的记录

#### Scenario: 带前置校验的迁移
- GIVEN 迁移请求声明了期望的来源状态
- WHEN 对象当前状态与期望来源状态不一致
- THEN 系统 SHALL 拒绝该次迁移并返回失败，MUST NOT 强制写入目标状态

### Requirement: 状态可查询与可运维
系统 SHALL 提供按对象 ID 查询状态、按状态筛选对象、列出最近编排记录的能力，并 SHALL 提供命令行运维入口用于查询、重放与重置。

#### Scenario: 查询阻断中的对象
- GIVEN 存在多个处于 `blocked` 的对象
- WHEN 运维按状态筛选
- THEN 系统 SHALL 返回该状态下的对象列表及其最近一次状态变更时间

### Requirement: 幂等保障
系统 MUST 对事件、卡片回调、编排三类入口做幂等，键格式分别为 `event:{event_id}`、`card_callback:{callback_token}`、`pipeline:{source_id}`。幂等记录 SHALL 持久化于 `data/idempotency/` 且保留期为 7 天，过期记录 SHALL 可清理。

#### Scenario: 幂等记录过期后重放
- GIVEN 某幂等记录已超过 7 天保留期并被清理
- WHEN 同一键的请求再次到达
- THEN 系统 SHALL 按新请求正常处理，MUST NOT 因缺失记录而报错

### Requirement: 重试与退避
系统 SHALL 对可重试的外部调用失败自动重试，最大次数由 `MAX_RETRIES`（默认 5）控制，退避为指数增长（基准 `RETRY_BASE_DELAY`，上限 60 秒）并叠加随机抖动。仅超时、连接错误与飞书限流类错误 SHALL 被重试；业务参数错误 MUST NOT 重试。

#### Scenario: 飞书限流
- GIVEN 飞书接口返回限流错误
- WHEN 系统处理该失败
- THEN 系统 SHALL 按指数退避加抖动重试，直至成功或达到 `MAX_RETRIES`

#### Scenario: 参数错误不重试
- GIVEN 外部接口返回参数非法类业务错误
- WHEN 系统处理该失败
- THEN 系统 SHALL 立即判定失败并记录，MUST NOT 消耗重试次数

### Requirement: 集成日志与脱敏
系统 SHALL 为每次入向 / 出向调用记录集成日志，字段包含 `log_id`、`timestamp`、`direction`、`interface`、`status`、`input_data`、`output_data`、`error`、`duration_ms`、`request_id`，按天落盘为 JSONL。日志 MUST 对 token、secret、password、api_key、access_token 等敏感字段脱敏。

#### Scenario: 出向调用携带凭据
- GIVEN 一次出向调用的请求体中含 `access_token`
- WHEN 系统写入集成日志
- THEN 日志中该字段 SHALL 被脱敏，MUST NOT 出现明文凭据

#### Scenario: 失败可追溯
- GIVEN 某次编排在提交平台阶段失败
- WHEN 运维排查该次编排
- THEN 系统 SHALL 可通过 `request_id` 定位入向事件与出向调用的完整链路日志

### Requirement: 运行模式隔离
系统 SHALL 通过 `RUN_MODE` 区分运行模式，默认为 `mock`。`mock` 模式下 MUST NOT 发起任何真实飞书 / Aily / 平台调用；切换为真实模式 MUST 依赖显式配置的凭据，缺失凭据时 SHALL 启动即失败并明确报错，MUST NOT 静默退回 mock。

#### Scenario: 默认零凭据可运行
- GIVEN 未配置任何飞书或 Aily 凭据
- WHEN 系统启动并执行完整主链路演示
- THEN 系统 SHALL 以 mock 模式跑通全链路，所有外部调用 SHALL 由本地模拟返回

#### Scenario: 真实模式缺失凭据
- GIVEN `RUN_MODE=real` 但 `FEISHU_APP_ID` 未配置
- WHEN 系统启动
- THEN 系统 SHALL 启动失败并提示缺失的配置项名称，MUST NOT 以 mock 行为伪装成真实运行

### Requirement: 演示数据标注
所有 mock 数据、样例输出与评测样例 MUST 标注为「脱敏模拟 / 原型样例」，MUST NOT 表述为真实企业数据或真实收益。

#### Scenario: 演示脚本输出
- GIVEN 运行端到端演示脚本
- WHEN 系统输出链路结果与指标
- THEN 输出 SHALL 显式标注数据为脱敏模拟样例
