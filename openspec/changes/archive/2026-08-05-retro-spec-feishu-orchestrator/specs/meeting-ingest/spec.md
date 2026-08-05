# meeting-ingest 规格增量

## ADDED Requirements

### Requirement: Webhook 端点
系统 SHALL 暴露三个 HTTP 端点：`POST /webhook/event`（飞书事件订阅）、`POST /webhook/card`（卡片回调）、`GET /health`（健康检查）。监听地址与端口 SHALL 由 `SERVER_HOST`（默认 `0.0.0.0`）与 `SERVER_PORT`（默认 `8080`）配置。

#### Scenario: 飞书订阅地址校验
- GIVEN 飞书平台向 `/webhook/event` 或 `/webhook/card` 发送含 `challenge` 字段的校验请求
- WHEN 系统解析请求体
- THEN 系统 SHALL 原样回显 `challenge` 且 MUST NOT 进入事件路由与幂等记录

#### Scenario: 健康检查
- GIVEN 服务已启动
- WHEN 调用 `GET /health`
- THEN 系统 SHALL 返回 200 与运行状态 JSON

### Requirement: 回调验签
系统 MUST 在 `RUN_MODE=real` 下对 `/webhook/event` 与 `/webhook/card` 的请求验签：签名为 `sha256(timestamp + nonce + encrypt_key + raw_body)` 的小写十六进制摘要，其中 `timestamp` / `nonce` / 待比对签名分别取请求头 `X-Lark-Request-Timestamp` / `X-Lark-Request-Nonce` / `X-Lark-Signature`，密钥取 `CARD_CALLBACK_ENCRYPT_KEY`。摘要比较 MUST 使用常量时间比较。验签失败 MUST 返回 401 且 MUST NOT 进入事件路由。验签函数 MUST NOT 以恒真桩实现存在于生产路径。

#### Scenario: 签名不匹配
- GIVEN `RUN_MODE=real` 且请求头 `X-Lark-Signature` 与本地计算结果不一致
- WHEN 系统处理该请求
- THEN 系统 SHALL 返回 401、记录失败集成日志，且不触发任何飞书或平台调用

#### Scenario: 密钥未配置
- GIVEN `RUN_MODE=real` 但 `CARD_CALLBACK_ENCRYPT_KEY` 为空
- WHEN 系统处理请求
- THEN 系统 SHALL 判定验签失败并返回 401，MUST NOT 因密钥缺失而放行（空密钥会使签名退化为可伪造的固定哈希）

#### Scenario: 重放超期请求
- GIVEN 请求签名有效但 `X-Lark-Request-Timestamp` 超出 300 秒时间窗
- WHEN 系统验签
- THEN 系统 SHALL 判定失败并返回 401

#### Scenario: mock 模式跳过验签
- GIVEN `RUN_MODE=mock`
- WHEN 请求未携带签名头
- THEN 系统 SHALL 跳过验签继续处理，并在启动日志中显式提示验签已跳过

### Requirement: 事件路由
系统 SHALL 注册并处理三类事件：`meeting.ended_v1`、`minutes.minute.generated_v1`、`card.action_triggered`。未注册的事件类型 SHALL 被记录并安全忽略，MUST NOT 抛出未捕获异常导致端点 5xx。

#### Scenario: 会议结束事件
- GIVEN 收到 `meeting.ended_v1`
- WHEN 系统路由该事件
- THEN 系统 SHALL 将该 `meeting_id` 的编排状态置为 `waiting_minutes` 并保留原始事件体

#### Scenario: 妙记生成事件
- GIVEN 收到 `minutes.minute.generated_v1` 且其 `meeting_id` 已存在处于 `waiting_minutes` 的记录
- WHEN 系统路由该事件
- THEN 系统 SHALL 将妙记与该会议关联并把状态迁移为 `minutes_ready`

#### Scenario: 妙记事件无对应会议
- GIVEN 收到 `minutes.minute.generated_v1` 但找不到对应会议记录
- WHEN 系统路由该事件
- THEN 系统 SHALL 以 `minutes:{minute_token}` 为对象 ID 新建记录，MUST NOT 丢弃该事件

### Requirement: 事件幂等
系统 MUST 在处理事件前以 `event:{event_id}` 为键做幂等判定；已处理过的事件 SHALL 直接返回成功且 MUST NOT 重复触发下游编排。

#### Scenario: 飞书重投同一事件
- GIVEN 某 `event_id` 已被成功处理并落幂等记录
- WHEN 飞书因超时重投同一事件
- THEN 系统 SHALL 返回成功、记录一次幂等命中，且不重复调用 Aily 或平台

### Requirement: 妙记读取与 MeetingPackage 组装
系统 SHALL 支持按妙记 URL、妙记 token、会议 ID 三种入口读取妙记详情，并组装为符合 `contracts/meeting-package.schema.json` 的 `MeetingPackage`。缺失字段 MUST 显式置空，MUST NOT 伪造内容。

#### Scenario: 按妙记 URL 触发主链路
- GIVEN 提供一条妙记 URL
- WHEN 系统读取妙记详情并组装
- THEN 系统 SHALL 产出含 `schema_version`、`source`、`source_object_id`、`title`、`content.transcript[]`、`source_url`、`captured_at` 的 `MeetingPackage`

#### Scenario: 逐字稿缺失
- GIVEN 妙记详情中不含逐字稿
- WHEN 系统组装 `MeetingPackage`
- THEN `content.transcript` SHALL 为空数组，系统 SHALL 记录失败原因并终止编译，MUST NOT 用摘要文本冒充逐字稿

### Requirement: 主链路编排顺序
系统 SHALL 按固定顺序执行主链路：读取妙记 → 组装 `MeetingPackage` → Aily 编译 → 提交平台 → 下发复核卡片。任一步失败 SHALL 将编排状态置为 `failed` 并记录失败阶段与错误。

#### Scenario: 编排幂等
- GIVEN 同一 `source_id` 的编排已成功完成并落 `pipeline:{source_id}` 幂等记录
- WHEN 再次以同一妙记触发编排
- THEN 系统 SHALL 返回上次的编排结果，MUST NOT 重复提交平台或重复下发卡片

#### Scenario: 未指定复核人
- GIVEN 编排调用未提供 `reviewer_id`
- WHEN 平台提交成功
- THEN 系统 SHALL 跳过卡片下发并将最终状态置为 `submitted`（而非 `reviewing`）
