# Proposal: 扩展行动审计权限、待处理通知与护照时间线

## Why

当前 `labmemory-platform` 在三个维度上与产品语义存在偏差，导致执行人无法独立完成行动审计闭环、关键状态变更后相关用户在控制塔看不到待办、实验护照时间线缺失操作记录：

1. **角色权限**：`app/services/permissions.py` 中 executor 只能 `start_task / fill_actual_params / submit_result`，而 `app/api/web/endpoints/audit.py` 把触发审计、更新审计上下文、确认重审、一键修正分别挂到 `review_candidate` / `handle_block` 两个 lead 专属权限上。结果是 executor 在前端 `AuditScreen` 能进入页面但点不动任何按钮，必须 lead 代为操作。这与「执行人是行动审计的执行主体」语义相悖。
2. **待处理通知**：`GET /web/control-tower` 仅 PI 可访问，`needs_action` 只列 blocked 任务和 pending_review 候选。一键修正后产生的新任务、提交结果后产生的待知识复核结果、冻结结果、需确认任务都不会按角色出现在相关用户的待处理页面上。
3. **护照时间线**：`app/services/passport.py` 的 timeline 只聚合业务对象（meeting/candidate/claim/decision/task/result/failure/version/card），不包含 AuditEvent。但用户要求「每一步操作的记录和修改的内容在实验护照中展示完整且正确」——审计上下文更新、一键修正、任务启动、结果复核等操作记录应当作为时间线一部分可见。

## What Changes

- **新增** 平台权限 `operate_action_audit`，含义为「操作行动审计」（触发审计、更新审计上下文、确认重审、一键修正）。executor / lead / pi / system 均拥有此权限。
- **修改** `app/api/web/endpoints/audit.py` 中四个写操作端点：`POST /tasks/{id}/audit`、`PUT /tasks/{id}/audit-context`、`POST /tasks/{id}/confirm`、`POST /tasks/{id}/fix` 全部改用 `operate_action_audit` 校验。`GET` 端点保持 `view_experiment`。
- **修改** `GET /web/control-tower`：开放给 lead / executor；`needs_action` 按角色返回相关待处理对象：
  - executor：自己 owner 的 `needs_confirmation / approved / running` 任务 + 自己提交的 `frozen` 结果
  - lead / pi：项目内 `pending_review / ready_to_publish / needs_info` 候选 + `blocked` 任务 + `linked / frozen` 结果
  - 异常队列与 KPI 仍仅 PI 可见
- **修改** `app/services/passport.py`：聚合与该 experiment_ref 关联对象的所有 AuditEvent，作为 timeline 中 `object_type=audit_event` 的条目展示；包含 `action`、`actor`、`before_state`、`after_state`、`details`。
- **修改** 前端：
  - `Layout.tsx` / `App.tsx`：`/`（控制塔）开放给 lead / executor，作为 executor/lead 默认首页
  - `TowerScreen.tsx`：兼容 `type=result` 的待处理项；异常队列仅对 PI 显示
  - `AuditScreen.tsx`：executor 与 lead/pi 共享 `canReview`，能进入「补充上下文 / 一键修正 / 确认重审」分支
  - `PassportScreen.tsx`：渲染 `audit_event` 时间线条目，展示操作动作、操作者、前后状态、详情
  - `i18n/labels.ts`：新增 `audit_event` 对象类型与 `audit_action` 标签映射
- **不修改** `feishu-orchestrator/`、`openspec/specs/contracts/`、其他源真相规格、`app/contracts/` JSON Schema、`app/services/audit.py` 中五类检查逻辑与三态结论、`app/services/result.py` 中知识状态计算。

## Impact

- 4 个 spec 增量（platform-permissions / action-audit / control-tower / experiment-passport），均为 MODIFIED。
- 后端约 4 个文件改动：`permissions.py`、`audit.py` 端点、`control_tower.py` 端点、`passport.py` 服务。
- 前端约 5 个文件改动：`App.tsx`、`Layout.tsx`、`AuditScreen.tsx`、`TowerScreen.tsx`、`PassportScreen.tsx`、`i18n/labels.ts`、`types/index.ts`。
- 新增测试：executor 可触发/更新/确认/修正、控制塔按角色返回 needs_action、护照时间线包含 AuditEvent。
- 现有测试不受影响：`test_executor_cannot_activate_version` / `test_executor_cannot_confirm_knowledge_state` / `test_pi_cannot_submit_result` 等仍按原权限断言通过。
