## MODIFIED Requirements

### Requirement: 冲突检测
系统 SHALL 检测版本冲突、数值冲突、范围冲突、语义冲突、证据冲突、责任冲突；引用旧版本默认高风险阻断。**数值冲突** SHALL 界定为：发布后将出现「同 scope 同参数名、且未被本次发布 supersede 替换的多个 current 不同值」的并存歧义。经人工复核确认、按「参数版本按参数维度跟踪」替换唯一 current 的版本更新，SHALL NOT 构成数值冲突。检出真正的数值冲突 MUST 冻结发布由人工解决。

#### Scenario: 旧版本引用冲突
- GIVEN 任务计划参数引用已被替代的旧版本
- WHEN 系统执行冲突检测
- THEN 系统 SHALL 标记为「版本冲突」高风险，并交由行动前审计阻断

#### Scenario: 复核确认替换单条 current 不视为数值冲突
- GIVEN 实验 EXP-001 当前仅有一条 current 主张「温度 70℃」scope=S1
- WHEN 负责人经复核确认在同一 scope=S1 发布「温度 75℃」
- THEN 系统 SHALL 视为按参数版本替换（75℃ supersede 70℃，70℃ 置 superseded），SHALL NOT 判为数值冲突、SHALL NOT 冻结，MUST NOT 同时保留两条 current

### Requirement: 发布前冲突检测
系统 SHALL 在主张发布前检测 6 类冲突（PRD §10.5）：版本冲突（任务引用旧版本）、数值冲突（发布后将出现未被本次 supersede 替换的多个 current、同 scope 同参数不同值并存）、范围冲突（新结论 scope 与任务条件不匹配）、语义冲突（建议值被当最终参数）、证据冲突（原文/决策/结果矛盾）、责任冲突（操作者无权限）。检出数值/版本冲突时 SHALL 冻结发布并要求人工解决；其余按各自闸门降级。经复核确认替换单条 current 的版本更新按「参数版本按参数维度跟踪」处理，SHALL NOT 触发数值冲突冻结。

#### Scenario: 数值冲突冻结发布
- GIVEN 实验 EXP-001 存在不止一条未被本次发布替换的 current 主张、同 scope=S1 同参数「温度」取不同值（如 70℃ 与残留的 72℃，本次仅替换 70℃）
- WHEN 新候选在同一 scope=S1 发布「温度 75℃」，发布后 72℃ 仍将作为 current 残留
- THEN 系统 SHALL 检出数值冲突并冻结发布，MUST NOT 创建额外的 current

#### Scenario: 复核确认替换不冻结
- GIVEN 实验 EXP-001 当前仅有一条 current 主张「温度 70℃」scope=S1
- WHEN 负责人经复核确认在同一 scope=S1 发布「温度 75℃」（替换单条 current）
- THEN 系统 SHALL 允许发布：新主张置 current、旧主张 superseded，SHALL NOT 冻结
