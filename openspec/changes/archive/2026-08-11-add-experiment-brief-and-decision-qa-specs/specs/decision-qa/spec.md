## Purpose

可信知识问答：对实验当前有效主张做带权限前置过滤、状态过滤、关键词匹配、带出处引用、无可靠证据即拒答的检索式回答，避免把未经证实或已废弃的结论当作答案。

## ADDED Requirements

### Requirement: 问答权限前置过滤
系统 SHALL 在检索前按请求者角色过滤可见实验：`admin` / `pi` 可见全部实验；其他角色 MUST 仅检索其作为成员（`ExperimentMember`）的实验，跨权限实验内容不得出现在回答或引用中。

#### Scenario: 非成员实验不出现在检索范围
- GIVEN 用户 u_web 角色为 executor 且仅属于实验 EXP-001
- WHEN u_web 提问内容与仅属于他人权限的 EXP-002 主张相关
- THEN 系统 SHALL 仅在 EXP-001 范围内检索，EXP-002 的主张不会被匹配或引用

### Requirement: 问答状态过滤
系统 SHALL 仅检索 `current` 状态的主张；`superseded`、已结束或被替代的主张 SHALL NOT 被作为答案来源。

#### Scenario: 旧版本主张不作为答案
- GIVEN 实验 EXP-001 中主张 C001（80℃，superseded）与 C003（70℃，current）并存
- WHEN 用户询问「温度是多少」
- THEN 系统 SHALL 仅以 C003 作答，不得返回 C001

### Requirement: 关键词匹配与排序
系统 SHALL 将问题按空格/标点切分为关键词，对主张的标题、描述、参数名/值/单位与证据文本做包含计数，按得分降序取最高分主张作为答案；同分时取较新主张。

#### Scenario: 多主张命中取最高分
- GIVEN 关键词同时命中主张 C003（得分 3）与 C005（得分 1）
- WHEN 用户提交该问题
- THEN 系统 SHALL 以 C003 作为答案来源

### Requirement: 问答带出处引用
系统 SHALL 在答案中附带引用：支持该主张的已发布结果（最多 3 条，含 `result_id`、`knowledge_status`、`metrics`）与主张自身证据（最多 2 条，含 `speaker`、`text`）。

#### Scenario: 命中时附带引用
- GIVEN 主张 C003 有 2 条已发布支持结果与 3 条证据
- WHEN 用户提问且 C003 为最高分命中
- THEN 回答 SHALL 附带最多 3 条结果引用与 2 条证据引用

### Requirement: 无可靠证据时拒答
系统 SHALL 在无可匹配主张时返回 `refused=true` 与引导提示（建议补充实验编号、参数名称或适用范围）；问题为空时 SHALL 同样拒答。

#### Scenario: 无任何命中
- GIVEN 用户提问但所有可见实验的 `current` 主张均无关键词命中
- WHEN 用户提交该问题
- THEN 响应 SHALL 为 `refused=true`，并附 `retrieval_scope` 中说明 `reason=no_match`

#### Scenario: 空问题
- GIVEN 用户提交空字符串或仅空白字符作为问题
- WHEN 系统处理该请求
- THEN 响应 SHALL 为 `refused=true`，`retrieval_scope.reason` 为 `empty_question`

### Requirement: 答案内容结构
系统 SHALL 在命中时输出包含实验编号、主张 ID、知识状态、参数版本号与参数列表的回答，并在 `retrieval_scope` 中回显检索者身份、检索实验数与过滤状态。

#### Scenario: 命中时输出结构化答案
- GIVEN 用户提问且最高分命中主张 C003（实验 EXP-001，知识状态 current，参数版本 v2）
- WHEN 系统生成回答
- THEN 回答 SHALL 包含实验编号 EXP-001、主张 ID C003、知识状态与参数版本 v2 及参数列表，`retrieval_scope` SHALL 含 `identity`、`searched_experiments`、`status_filter`
