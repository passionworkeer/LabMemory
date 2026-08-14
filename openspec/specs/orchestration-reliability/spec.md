# orchestration-reliability Specification

## Purpose
TBD - created by archiving change retro-spec-feishu-orchestrator. Update Purpose after archive.
## Requirements
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

### Requirement: 运行模式隔离
系统 SHALL 通过 `RUN_MODE` 区分运行模式，默认为 `mock`。`mock` 模式下 MUST NOT 发起任何真实飞书 / Aily / 平台调用。切换为真实模式 MUST 依赖显式配置的凭据，缺失凭据时 SHALL 明确报错，MUST NOT 静默退回 mock。

凭据来源按调用目标区分，MUST NOT 混用：

- **飞书调用**：凭据由 `lark-cli` 自身管理（`lark-cli config bind` / `config init` + `auth login`，存于操作系统钥匙串）。系统 MUST NOT 从 `.env` 读取或向 CLI 传递飞书 access token。
- **Aily 与平台调用**：走 HTTP，凭据 MUST 来自 `config/.env`（`AILY_API_KEY`、`PLATFORM_API_KEY`）。

#### Scenario: 默认零凭据可运行
- GIVEN 未配置任何飞书或 Aily 凭据
- WHEN 系统启动并执行完整主链路演示
- THEN 系统 SHALL 以 mock 模式跑通全链路，所有外部调用 SHALL 由本地模拟返回

#### Scenario: 真实模式缺失凭据
- GIVEN `RUN_MODE=real` 但 Aily 或平台的 API Key 未配置
- WHEN 系统发起对应调用
- THEN 系统 SHALL 失败并提示缺失的配置项名称，MUST NOT 以 mock 行为伪装成真实运行

#### Scenario: 飞书凭据不在 .env 中
- GIVEN `RUN_MODE=real` 且 `lark-cli` 已完成绑定与授权
- WHEN 系统发起飞书调用
- THEN 系统 SHALL 仅通过 `--as user|bot` 声明身份并由 CLI 解析凭据，`.env` 中的飞书 token 字段 SHALL 不参与调用

### Requirement: 演示数据标注
所有 mock 数据、样例输出与评测样例 MUST 标注为「脱敏模拟 / 原型样例」，MUST NOT 表述为真实企业数据或真实收益。

#### Scenario: 演示脚本输出
- GIVEN 运行端到端演示脚本
- WHEN 系统输出链路结果与指标
- THEN 输出 SHALL 显式标注数据为脱敏模拟样例

### Requirement: 幂等占位原子化
系统 SHALL 用原子文件创建（`O_CREAT|O_EXCL`）作为幂等占位令牌：业务执行前先尝试创建占位文件，创建成功者获得执行权，失败者视为已处理。MUST NOT 采用「检查→业务→标记」三步非原子序列（存在 TOCTOU 竞态，并发/重试下可重复执行建任务等副作用）。

#### Scenario: 并发同 token 仅执行一次
- GIVEN 两个并发回调携带相同 token
- WHEN 两者同时进入幂等检查
- THEN 系统 SHALL 仅允许其中一个执行业务副作用，另一个直接返回已处理结论

### Requirement: 重试按 HTTP 状态分类
系统 SHALL 按可恢复性分类错误以决定重试：仅 5xx（500/502/503/504）与 429 重试；4xx（除 429）判为不可恢复并立即失败。错误包装 MUST 保留原始 HTTP code，MUST NOT 仅依赖响应体字面字符串（如 "rate limit"）判定。

#### Scenario: 400 不重试
- GIVEN 平台返回 HTTP 400（业务校验错）
- WHEN 编排器重试引擎处理
- THEN 系统 MUST NOT 重试， SHALL 立即抛出不可恢复错误

### Requirement: 卡片回调受理与后续动作分离标记
系统 SHALL 在平台回调转发成功（获得平台响应）后**立即**标记回调「已受理」，与「后续飞书任务创建/卡片发送完成」分离。后续动作失败重试时，平台侧 token 幂等返回首次结论，但编排器 MUST NOT 重复执行建任务等副作用。

#### Scenario: 回调受理后建任务失败不重复
- GIVEN 平台回调返回 approved+pass，编排器标记受理后建飞书任务失败
- WHEN 重试该回调
- THEN 系统 SHALL 跳过 `_handle_approved` 的建任务副作用（已受理），MUST NOT 二次建任务

### Requirement: real Aily 路径确定性规则
系统 SHALL 在 real Aily 编译路径（非仅 mock）应用确定性规则：experiment_ref 编号格式校验、参数数值范围校验、版本号校验。MUST NOT 直接采信 Aily 原始输出而不校验。

#### Scenario: real 路径校验编号格式
- GIVEN real Aily 返回 candidate 的 experiment_ref 格式非法
- WHEN 编排器组装 CandidatePackage
- THEN 系统 SHALL 校验失败并标记，MUST NOT 原样透传

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

### Requirement: 失败状态记录在正确的对象键下

流水线任一步骤失败时，FAILED 状态 MUST 记录在该流水线真实 `source_object_id` 对应的状态键下（仅当 source_object_id 尚未解析时才回退到来源 URL 键），状态查询 SHALL 能据此看到失败态而非陈旧的进行中状态。

#### Scenario: 提交平台失败后的状态可见

- GIVEN 妙记解析成功得到 source_id=S、已置 COMPILING
- WHEN 步骤 3 提交候选失败
- THEN `get_status(S)` SHALL 返回 failed 态（而非停留在 compiling/submitted）

### Requirement: 事件与流水线处理权原子抢占

事件路由与流水线主链路 MUST 在执行业务副作用前以原子占位（O_CREAT|O_EXCL）抢占处理权；抢占失败视为重复投递返回既有结论；处理异常时 MUST 释放占位允许重试，处理成功后 MUST 写入含结果的完成标记。

#### Scenario: 并发重复事件仅处理一次

- GIVEN 同一 event_id 的两个事件并发到达
- THEN 仅一个 SHALL 获得处理权执行副作用，另一个 SHALL 返回 duplicate

#### Scenario: 处理崩溃后可重试

- GIVEN 处理方获得占位后、写入完成标记前进程异常退出且异常被捕获
- THEN 占位 SHALL 被释放，重试投递可重新处理

### Requirement: 状态快照原子写入

状态机快照 MUST 以「写临时文件 + 原子替换」方式持久化；崩溃半写 SHALL NOT 损坏既有快照。

#### Scenario: 写入中断不丢历史

- GIVEN 对象 O 已有含 history 的快照
- WHEN 一次状态写入在半途崩溃
- THEN 重新读取 SHALL 得到完整旧快照或完整新快照，不得为空/损坏

### Requirement: mock 模式的回源限制

RUN_MODE=mock 时，除本机回环地址限制外，系统 MUST 拒绝携带 `X-Forwarded-For` 头的请求（防反代/容器旁路验签）；webhook 请求体大小 MUST 有上限（1MB）。

#### Scenario: 反代转发的请求在 mock 下被拒

- GIVEN RUN_MODE=mock，请求来自 127.0.0.1 但携带 X-Forwarded-For: 203.0.113.5
- THEN 请求 SHALL 被拒绝（403），不得进入验签旁路处理

