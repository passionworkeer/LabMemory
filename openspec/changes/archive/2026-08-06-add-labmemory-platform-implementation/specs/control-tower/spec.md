# control-tower Specification

## ADDED Requirements

### Requirement: 研发控制塔看板
系统 SHALL 在 `GET /web/control-tower` 返回首页看板数据，包含待复核候选数、行动前阻断数、接口/证据异常数、24h 知识发布率、当前执行实验数；所有指标 MUST 标注数据来源（模拟/评测/生产），MUST NOT 伪装真实企业收益。

#### Scenario: 看板返回 KPI
- GIVEN 平台已有种子数据
- WHEN 前端调用 `GET /web/control-tower`
- THEN 响应 SHALL 包含 `kpis`（待复核/阻断/异常/发布率/执行实验）、`needs_action`（待处理对象列表）、`anomalies`（异常队列）

### Requirement: 异常队列
系统 SHALL 维护异常队列，包含接口延迟、证据失效、版本关联错误、重复事件、模型质量五类；每条异常 MUST 记录来源事件、业务对象、当前状态、重试历史、责任人、下一动作。

#### Scenario: 异常重试
- GIVEN 异常 EVT-2098（HPLC 链接失效）状态为「待修复」
- WHEN 责任人调用 `POST /web/anomalies/{id}/retry`
- THEN 系统 SHALL 重新执行关联的 IntegrationAction，更新状态为「重试中」或「已完成」

### Requirement: 演示数据标注
所有看板指标与异常 MUST 标注「脱敏模拟 / 原型样例」，MUST NOT 表述为真实企业数据。

#### Scenario: 看板响应含标注
- GIVEN 任何 `GET /web/control-tower` 调用
- WHEN 系统返回响应
- THEN 响应 SHALL 包含 `data_source: "脱敏模拟样例"` 字段
