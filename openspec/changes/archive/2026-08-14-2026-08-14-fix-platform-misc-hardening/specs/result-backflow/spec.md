## ADDED Requirements

### Requirement: 结果冻结的参数覆盖判定

实际参数判定为「覆盖计划参数」MUST 同时满足键存在且值非空（非 null/空串）；任一计划参数键缺失或值为空时，结果 SHALL 冻结（frozen）。

#### Scenario: 空值不视为覆盖

- GIVEN 任务计划参数含 temperature/concentration/time，提交 actual_params={"temperature": "70", "concentration": null, "time": "2"}
- THEN 结果 SHALL 判 frozen（concentration 值为空不算覆盖）
