## MODIFIED Requirements

### Requirement: 重试与退避
系统 SHALL 对所有纳入可靠性边界的可重试外部调用失败自动重试，最大次数由 `MAX_RETRIES`（默认 5）控制，退避为指数增长（基准 `RETRY_BASE_DELAY`，上限 60 秒）并叠加随机抖动。可重试判定 MUST 覆盖超时、连接错误与飞书限流类错误，包括 CLI subprocess 超时和明确标记的网络异常；业务参数错误、授权配置错误和响应契约错误 MUST NOT 重试。每次尝试和最终失败 SHALL 可通过集成日志追踪。

#### Scenario: CLI 超时重试
- GIVEN 纳入可靠性边界的 lark-cli 调用发生 subprocess 超时
- WHEN 系统处理该失败
- THEN 系统 SHALL 按指数退避加抖动重试，直至成功或达到 `MAX_RETRIES`

#### Scenario: 飞书限流
- GIVEN 飞书接口返回限流错误
- WHEN 系统处理该失败
- THEN 系统 SHALL 按指数退避加抖动重试，直至成功或达到 `MAX_RETRIES`

#### Scenario: 参数错误不重试
- GIVEN 外部接口返回参数非法类业务错误
- WHEN 系统处理该失败
- THEN 系统 SHALL 立即判定失败并记录，MUST NOT 消耗重试次数

#### Scenario: 参数或响应契约错误不重试
- GIVEN 外部接口返回参数非法、授权失败或响应缺少必填字段
- WHEN 系统处理该失败
- THEN 系统 SHALL 立即判定失败并记录，MUST NOT 消耗重试次数

### Requirement: 集成日志与脱敏
系统 SHALL 为每次纳入可靠性边界的入向 / 出向调用记录开始、重试、成功或失败集成日志，字段包含 `log_id`、`timestamp`、`direction`、`interface`、`status`、`input_data`、`output_data`、`error`、`duration_ms`、`request_id`，按天落盘为 JSONL。日志 MUST 对 token、secret、password、api_key、access_token 以及命令参数中的敏感值脱敏。

#### Scenario: 关键卡片调用失败可追溯
- GIVEN 真实模式下发送审批、阻断、告警卡片或更新卡片失败
- WHEN 运维排查该调用
- THEN 系统 SHALL 找到对应接口的失败日志和重试记录，且日志不得包含明文凭据

#### Scenario: 出向调用携带凭据
- GIVEN 一次出向调用的请求体中含 `access_token`
- WHEN 系统写入集成日志
- THEN 日志中该字段 SHALL 被脱敏，MUST NOT 出现明文凭据

#### Scenario: 失败可追溯
- GIVEN 某次编排在任一纳入可靠性边界的出向阶段失败
- WHEN 运维排查该次编排
- THEN 系统 SHALL 可通过 `request_id` 定位完整调用链路

## ADDED Requirements

### Requirement: 外部副作用幂等
对于任务创建和批量台账写入等可产生外部副作用的操作，系统 MUST 使用稳定业务键或执行前查询/记录机制避免客户端超时后重试造成重复资源。重试失败时系统 SHALL 保留可恢复信息，MUST NOT 将已部分成功的批量操作伪装成全量失败且不可追踪。

#### Scenario: 任务创建响应超时后重试
- GIVEN 飞书服务端已创建任务但客户端在响应返回前超时
- WHEN 系统恢复或重试同一候选任务
- THEN 系统 SHALL 通过稳定业务键或已存在任务查询复用原任务，MUST NOT 创建重复任务

#### Scenario: 批量台账部分成功
- GIVEN 批量写入在中途失败且前序记录已创建
- WHEN 系统记录失败结果
- THEN 系统 SHALL 保留已创建记录标识和失败位置，支持后续恢复，MUST NOT 无信息地重复创建前序记录
