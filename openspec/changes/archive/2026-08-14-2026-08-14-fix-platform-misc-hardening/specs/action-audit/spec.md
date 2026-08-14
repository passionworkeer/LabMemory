## ADDED Requirements

### Requirement: 证据与范围检查的完整语义

行动前审计中「证据与范围」检查 MUST 要求计划参数版本的 scope 与 parameters 均非空（AND 语义）；任一缺失时该检查 SHALL 判 blocked 并指明缺失项。

#### Scenario: 仅 parameters 无 scope

- GIVEN 任务计划参数版本仅含 parameters、scope 为 None
- WHEN 行动前审计执行
- THEN 证据与范围检查 SHALL 判 blocked 并提示补充适用范围
