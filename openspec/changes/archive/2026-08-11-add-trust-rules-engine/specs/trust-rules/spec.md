# trust-rules Specification Delta

## ADDED Requirements

### Requirement: 候选发布前六道闸门校验
系统 SHALL 在候选确认为正式主张前（`confirm_review` 与 `/api/v1/card/callback` 的 approve 路径）运行六道闸门：对象门（experiment_ref 明确）/参数门（parameters 非空且每项有 name+value）/证据门（evidence 非空且每条有 text）/范围门（scope 明确）/状态门（不含暂定/建议关键词）/责任门（操作者是实验成员）。任一失败时系统 MUST NOT 将主张置为 `current`，SHALL 按 PRD §10.1 降级：对象/参数/范围/责任门失败→`pending_supplement`（待补充）；证据/状态门失败→`pending_validation`（待验证）。

#### Scenario: 全部门通过发布为 current
- GIVEN 候选 cand_a 含 experiment_ref、完整 parameters、evidence、scope，操作者为实验成员，标题不含暂定词
- WHEN 确认发布
- THEN 主张 SHALL 为 `current` 且生成任务草稿

#### Scenario: 证据不足降级待验证
- GIVEN 候选 cand_b 的 evidence 为空
- WHEN 确认发布
- THEN 主张 SHALL 为 `pending_validation`，MUST NOT 生成可执行任务，响应 SHALL 携带「证据门失败」

#### Scenario: 暂定表达降级待验证
- GIVEN 候选 cand_c 标题为「温度 80℃ 暂定」
- WHEN 确认发布
- THEN 主张 SHALL 为 `pending_validation`（语义栅栏，PRD line 854），MUST NOT 成为当前有效参数

### Requirement: 语义栅栏禁止暂定表达生效
系统 SHALL 识别候选标题/描述中的暂定/建议关键词（`可以试试`/`建议`/`可能`/`暂定`/`试试`/`或许`/`考虑`），命中时 MUST NOT 允许该候选成为 `current` 主张（PRD line 854）。

#### Scenario: 可以试试 不生效
- GIVEN 候选描述含「可以试试 0.8 eq」
- WHEN 确认发布
- THEN 系统 SHALL 降级为 `pending_validation`，MUST NOT 置为 current

### Requirement: 发布前冲突检测
系统 SHALL 在主张发布前检测 6 类冲突（PRD §10.5）：版本冲突（任务引用旧版本）、数值冲突（同 scope 同参数名存在多个 current 不同值）、范围冲突（新结论 scope 与任务条件不匹配）、语义冲突（建议值被当最终参数）、证据冲突（原文/决策/结果矛盾）、责任冲突（操作者无权限）。检出数值/版本冲突时 SHALL 冻结发布并要求人工解决；其余按各自闸门降级。

#### Scenario: 数值冲突冻结发布
- GIVEN 实验 EXP-001 已有 current 主张「温度 70℃」scope=S1
- WHEN 新候选在同一 scope=S1 发布「温度 75℃」
- THEN 系统 SHALL 检出数值冲突并冻结发布，MUST NOT 创建第二条 current

### Requirement: 非当前主张不参与问答与默认检索
系统 SHALL 在可信问答（`/api/qa/ask`）与实验护照 current_claim 中仅采用 `current` 状态主张；`pending_supplement`/`pending_validation`/`superseded` MUST NOT 作为答案来源或当前主张，但 SHALL 在审计与护照时间线中可见。

#### Scenario: 待验证主张不作为问答答案
- GIVEN 实验 EXP-001 有主张 C_old（pending_validation，80℃）与 C_cur（current，70℃）
- WHEN 用户提问「温度是多少」
- THEN 系统 SHALL 仅以 C_cur 作答，MUST NOT 返回 C_old
