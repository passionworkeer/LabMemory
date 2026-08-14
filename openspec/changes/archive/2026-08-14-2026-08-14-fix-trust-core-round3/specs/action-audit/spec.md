## ADDED Requirements

### Requirement: 任务启动前复查版本时效

`start_task` MUST 在放行前复查任务绑定主张仍是其实验的 current 且 `knowledge_status` 不属于 {refuted, replaced, insufficient_evidence}；不满足时任务 SHALL 置为 needs_confirmation 并返回版本差异与一键修正路径，不得进入 running。

#### Scenario: 审计通过后主张被替代

- GIVEN 任务 T 审计 passed、状态 audited、绑定主张 C1
- WHEN C1 被新主张 C2 替代（C1→superseded）后用户启动 T
- THEN 启动 SHALL 被拒绝，T 置 needs_confirmation，响应含一键修正提示

#### Scenario: 绑定主张已被实验推翻

- GIVEN 任务 T 绑定的 current 主张被结果发布标为 refuted
- WHEN 用户启动 T
- THEN 启动 SHALL 被拒绝并提示主张已被推翻

### Requirement: 审计写路径并发保护

行动前审计的一键修正与审计执行写路径 MUST 纳入按实验的写锁临界区，防止并发重复创建修正任务或重复插入审计记录。

#### Scenario: 并发一键修正

- GIVEN 同一 blocked 任务收到两个并发一键修正请求
- THEN 仅一个 SHALL 创建修正任务，另一个 SHALL 返回已存在修正的提示
