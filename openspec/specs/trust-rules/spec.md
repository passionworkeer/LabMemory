# Trust Rules Specification

## Purpose
以确定性规则（而非大模型）管理主张、参数版本、任务、结果的可信状态、版本演进与冲突检测，确保进入实验的知识可审计、可追溯、可更新。
## Requirements
### Requirement: 六道质量闸门
系统 SHALL 在候选发布为正式对象前，依次执行对象门、参数门、证据门、范围门、状态门、责任门；任一闸门失败，该候选 MUST NOT 成为生效参数或正式任务。

#### Scenario: 缺少有效证据
- GIVEN 一条候选主张无有效证据锚点
- WHEN 系统执行证据门
- THEN 该候选 SHALL 只能保留为「候选」或「待验证」，不得标记「当前有效」

### Requirement: 主张状态机
系统 SHALL 维护主张状态：候选 → 待补充 / 待复核 / 待验证 → 当前有效 / 部分支持 / 被推翻 / 被替代 / 已归档；Aily 仅能创建 `候选`，被替代的旧版本 MUST 保留且不被删除或静默覆盖。

#### Scenario: 新版本替代旧版本
- GIVEN 主张 C001（80℃ v1）已被 C003（70℃ v2）经审核替代
- WHEN 系统记录替代关系
- THEN C001 SHALL 标记为 `被替代` 并保留历史，C003 标记为 `当前有效`

### Requirement: 参数版本状态机
系统 SHALL 维护参数版本状态：草稿 → 待审核 → 生效 / 已过期 / 被替代 / 已驳回；同一适用范围、同一参数 MUST 仅存在一个 `生效` 版本。

#### Scenario: 同范围唯一生效版本
- GIVEN 参数「推荐温度」在 S1/0.20 mol/L/2h/催化剂 B 下已存在生效版本 70℃ v2
- WHEN 系统尝试将 80℃ v1 设为生效
- THEN 系统 SHALL 拒绝，80℃ v1 保持 `已过期` 或 `被替代`

### Requirement: 任务状态机
系统 SHALL 维护任务状态：草稿 → 待审计 →（需确认 | 已阻断 | 已批准）→ 执行中 → 已完成 / 已取消；`已阻断` 任务 MUST NOT 请求飞书创建正式任务。

#### Scenario: 已阻断任务不得请求创建飞书任务
- GIVEN 任务 T001 审计结果为 `已阻断`
- WHEN 系统尝试推进该任务
- THEN 系统 SHALL 不调用飞书任务创建接口，并将 T001 保留为 `已阻断` 状态

### Requirement: 冲突检测
系统 SHALL 检测版本冲突、数值冲突、范围冲突、语义冲突、证据冲突、责任冲突；引用旧版本默认高风险阻断，数值冲突 MUST 冻结发布由人工解决。

#### Scenario: 旧版本引用冲突
- GIVEN 任务计划参数引用已被替代的旧版本
- WHEN 系统执行冲突检测
- THEN 系统 SHALL 标记为「版本冲突」高风险，并交由行动前审计阻断

### Requirement: 三值留痕
系统 SHALL 对每条经人工复核的候选，分别保存原始会议表达、AI 候选值、人工确认值，且任何人工修改 MUST 记录修改人与原因（详见 decision-inbox 规格）。

#### Scenario: 人工修正记录修改人及原因
- GIVEN 负责人将某候选的 Aily 候选值修正为人工确认值
- WHEN 系统保存该候选的复核结果
- THEN 系统 SHALL 同时保留原始会议表达、AI 候选值与人工确认值，并记录修改人与修改原因

### Requirement: 任务状态机写操作前置校验
系统 SHALL 对任务状态写操作加前置守卫：`approve`/`reject` 仅允许非 `running`/`completed` 任务；`start` 仅允许 `audited`→`running`（禁止 `running`→`running` 覆盖）；`audit_fix` 一键修正后旧任务 MUST 置绑定当前主张或加 fix 锁防止重复生成草稿。MUST NOT 允许状态非法跳转。

#### Scenario: 不重复 start running 任务
- GIVEN 任务 T_x 已 `running`
- WHEN 再次调用 `POST /api/tasks/T_x/start`
- THEN 系统 SHALL 拒绝（返回状态错误），MUST NOT 覆盖 assignee/due_date

### Requirement: 版本门无当前主张判阻断
系统 SHALL 在六道闸门审计的版本门中，当任务绑定了主张但实验当前无 `current` 主张时（异常状态）判 `blocked`，MUST NOT 落入「视为通过」分支。

#### Scenario: current 主张缺失判阻断
- GIVEN 任务 T_x 绑定 claim C_old，但实验当前无任何 `current` 主张
- WHEN 审计版本门检查
- THEN 版本门 SHALL 返 `blocked`

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

