## ADDED Requirements

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
