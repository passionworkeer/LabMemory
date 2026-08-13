# Result Backflow Specification

## Purpose
将实验 / 检测结果回流，校验其与任务、参数版本的关系，并以非二元知识状态持续校正决策，沉淀失败边界与后续动作。
## Requirements
### Requirement: 计划与实际参数对比
系统 SHALL 分别记录计划参数与实际参数；实际偏差 MUST NOT 覆盖计划值。

#### Scenario: 实际参数偏离计划
- GIVEN 任务计划 65℃ 但实际执行 68℃
- WHEN 结果回流
- THEN 系统 SHALL 在时间线独立展示计划值与实际值，不相互覆盖

### Requirement: 非二元知识状态
系统 SHALL 将结果判定为 支持 / 部分支持 / 推翻 / 替代 / 证据不足；MUST NOT 使用简单「成功 / 失败」。

#### Scenario: 主指标改善但存在副作用
- GIVEN 65℃ 使转化率由 63% 升至 78%，但副产物由 4% 升至 9%
- WHEN 系统判定知识状态
- THEN 系统 SHALL 标记为「部分支持」，保留正向证据并增加副产物边界

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

### Requirement: 失败边界卡
系统 SHALL 为每个非完全成功的决策生成失败边界卡，包含失败现象、触发条件、排除因素、根因假设、避免策略、适用边界；根因假设 MUST 显式标记为「假设」，不得表述为事实。

#### Scenario: 副产物升高的失败边界
- GIVEN 升温导致副产物升高至 9%
- WHEN 系统生成失败边界卡 F001
- THEN 根因（高温与催化剂当量共同促进副反应）SHALL 标记为「假设」，并生成「降到 0.8 eq 复验」后续任务

### Requirement: 证据失效降级与停止推荐
系统 SHALL 在问答检索（`/api/qa/ask`）排除证据失效的 current 主张（PRD §13.1）。证据有效性定义为结构化非空（evidence 列表非空且每条含 text）。结果发布时若关联主张证据失效，系统 SHALL 提示采用 `insufficient_evidence`。真实 URL 可达性探活（需飞书文档权限）作为后续增强，本次实现结构化校验。

#### Scenario: 证据失效不作为问答答案
- GIVEN 实验 EXP-001 有 current 主张 C_x 但其 evidence 为空/残缺
- WHEN 用户提问命中 C_x
- THEN 系统 SHALL 排除 C_x（停止主动推荐），若无其他有效主张则拒答

