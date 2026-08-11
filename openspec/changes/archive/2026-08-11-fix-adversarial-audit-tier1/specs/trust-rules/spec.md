# trust-rules Specification Delta

## ADDED Requirements

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
