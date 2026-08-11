# orchestration-reliability Specification Delta

## ADDED Requirements

### Requirement: 流水线诚实状态与失败告警
系统 SHALL 在流水线提交候选后返回 `status:"submitted"`（如实反映「已提交待复核」，非「已完成」），MUST NOT 在仅完成提交时记录 `completed_at`。重试耗尽或编译失败时，系统 SHALL（若配置 reviewer）调用 `send_alert_card` 通知，而非静默置 FAILED。

#### Scenario: 提交后返回 submitted
- GIVEN 编排器成功向平台提交候选并发出复核卡
- WHEN 流水线返回结果
- THEN status SHALL 为 "submitted"，MUST NOT 含 completed_at

## ADDED Requirements

### Requirement: real Aily 路径确定性规则
系统 SHALL 在 real Aily 编译路径（非仅 mock）应用确定性规则：experiment_ref 编号格式校验、参数数值范围校验、版本号校验。MUST NOT 直接采信 Aily 原始输出而不校验。

#### Scenario: real 路径校验编号格式
- GIVEN real Aily 返回 candidate 的 experiment_ref 格式非法
- WHEN 编排器组装 CandidatePackage
- THEN 系统 SHALL 校验失败并标记，MUST NOT 原样透传
