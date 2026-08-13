## MODIFIED Requirements

### Requirement: 结果版本校验
系统 SHALL 在结果提交时校验实际参数是否完整覆盖任务的计划参数集合：实际参数键集 MUST 覆盖全部计划参数名且非空，否则系统 MUST 将结果冻结（`status=frozen`），不进入发布，直到人工核对并补齐实际参数。实际参数包含计划参数名之外的额外键 SHALL NOT 触发冻结——额外观测不构成版本/参数不匹配。

#### Scenario: 计划外参数不冻结
- GIVEN 任务计划参数为 temperature/time，执行人在结果中额外记录了 pH
- WHEN 结果回流提交 actual_params 含 temperature/time/pH
- THEN 系统 SHALL NOT 冻结，结果 status=submitted

#### Scenario: 版本错配冻结
- GIVEN 任务计划参数为 temperature/time/catalyst，执行人仅提交 temperature/time（未覆盖全部计划参数名）
- WHEN 结果回流
- THEN 系统 SHALL 将结果标记为 frozen，不生成知识，并提示补齐 catalyst 实际值
