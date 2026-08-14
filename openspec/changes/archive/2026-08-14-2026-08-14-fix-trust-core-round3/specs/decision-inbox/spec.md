## ADDED Requirements

### Requirement: 复核确认的并发串行化

复核状态检查与状态变更 MUST 完整位于按实验的写锁临界区内：进入临界区后复查 `review.status == "pending"`，非 pending SHALL 抛出状态转移错误。Web 复核路径与卡片回调 approve 路径 MUST 遵循同一串行化纪律。

#### Scenario: 并发确认同一会议

- GIVEN 会议 M 复核记录状态为 pending
- WHEN 两个确认请求并发到达
- THEN 仅第一个 SHALL 成功；第二个 SHALL 在锁内复查发现非 pending 并返回状态转移错误，不产生重复 Claim/Task

### Requirement: 卡片回调发布的主张进入检索索引

卡片回调 approve 路径生成 current 主张后，系统 SHALL 与 Web 复核路径一致地触发主张索引与会议证据索引；supersede 旧主张时 SHALL 同步把旧主张检索切片标记为 superseded。

#### Scenario: 卡片审批后的问答可见性

- GIVEN 候选经飞书卡片 approve 发布为 current 主张 C2，同实验旧主张 C1 被替代
- WHEN 用户向可信问答提问相关参数
- THEN 检索候选集 SHALL 含 C2 且不含 C1（C1 切片状态为 superseded）

### Requirement: 索引失败的可见性

主张/结果/证据索引更新失败时，系统 SHALL 记录告警日志（含失败对象与异常摘要），不得静默吞异常；失败不得阻断业务主流程。

#### Scenario: 索引异常留痕

- GIVEN 索引更新抛出异常
- WHEN 复核确认流程执行
- THEN 业务提交 SHALL 正常完成，且日志 SHALL 包含索引失败告警
