# result-backflow Specification Delta

## ADDED Requirements

### Requirement: 证据失效降级与停止推荐
系统 SHALL 在问答检索（`/api/qa/ask`）排除证据失效的 current 主张（PRD §13.1）。证据有效性定义为结构化非空（evidence 列表非空且每条含 text）。结果发布时若关联主张证据失效，系统 SHALL 提示采用 `insufficient_evidence`。真实 URL 可达性探活（需飞书文档权限）作为后续增强，本次实现结构化校验。

#### Scenario: 证据失效不作为问答答案
- GIVEN 实验 EXP-001 有 current 主张 C_x 但其 evidence 为空/残缺
- WHEN 用户提问命中 C_x
- THEN 系统 SHALL 排除 C_x（停止主动推荐），若无其他有效主张则拒答
