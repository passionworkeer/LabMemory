## MODIFIED Requirements

### Requirement: 任务状态机
系统 SHALL 维护任务状态：草稿 → 待审计 →（需确认 | 已阻断 | 已批准）→ 执行中 → 已完成 / 已取消；`已阻断` 任务 MUST NOT 请求飞书创建正式任务。

#### Scenario: 已阻断任务不得请求创建飞书任务
- GIVEN 任务 T001 审计结果为 `已阻断`
- WHEN 系统尝试推进该任务
- THEN 系统 SHALL 不调用飞书任务创建接口，并将 T001 保留为 `已阻断` 状态

### Requirement: 三值留痕
系统 SHALL 对每条经人工复核的候选，分别保存原始会议表达、AI 候选值、人工确认值，且任何人工修改 MUST 记录修改人与原因（详见 decision-inbox 规格）。

#### Scenario: 人工修正记录修改人及原因
- GIVEN 负责人将某候选的 Aily 候选值修正为人工确认值
- WHEN 系统保存该候选的复核结果
- THEN 系统 SHALL 同时保留原始会议表达、AI 候选值与人工确认值，并记录修改人与修改原因
