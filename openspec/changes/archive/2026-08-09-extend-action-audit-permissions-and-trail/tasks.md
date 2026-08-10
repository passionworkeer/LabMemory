# Tasks: 扩展行动审计权限、待处理通知与护照时间线

## M1 - OpenSpec change 与权限扩展

- [x] 创建 OpenSpec change `extend-action-audit-permissions-and-trail`（proposal + design + 4 spec 增量 + tasks）
- [x] `openspec validate extend-action-audit-permissions-and-trail` 通过
- [x] `app/services/permissions.py` 新增 `operate_action_audit` 权限项；executor / lead / pi 都拥有；lead/pi 同时保留 `view_control_tower`
- [x] executor 增加 `view_control_tower` 权限，使其能访问 `/web/control-tower`
- [x] 单测：`tests/permission/test_executor_action_audit.py` 覆盖 executor 可触发审计、可更新审计上下文、可一键修正、可确认重审

## M2 - 行动审计端点权限切换

- [x] `app/api/web/endpoints/audit.py`：
  - `POST /tasks/{id}/audit` 改用 `operate_action_audit`
  - `PUT /tasks/{id}/audit-context` 改用 `operate_action_audit`
  - `POST /tasks/{id}/confirm` 改用 `operate_action_audit`
  - `POST /tasks/{id}/fix` 改用 `operate_action_audit`
  - `GET` 端点保持 `view_experiment`
- [x] `tests/business/test_flow_action_audit.py` 复用现有断言（lead 登录仍可通过）

## M3 - 控制塔按角色返回待处理

- [x] `app/api/web/endpoints/control_tower.py`：
  - `needs_action` 按 user.role 与 owner 过滤
  - executor：owner==user_id 的 needs_confirmation/approved/running/pending_audit 任务 + 自己提交的 frozen 结果
  - lead/pi：项目内 pending_review/ready_to_publish/needs_info 候选 + blocked 任务 + linked/frozen 结果
  - anomalies 队列与重试端点仅 PI/system 可见，其他角色返回空数组或 403
- [x] `tests/business/test_control_tower_roles.py` 断言按角色过滤

## M4 - 实验护照时间线聚合 AuditEvent

- [x] `app/services/passport.py`：聚合该 experiment 关联对象的所有 AuditEvent，转为 timeline 中 `object_type=audit_event` 条目
- [x] timeline entry 新增字段：`action`、`target_type`、`target_id`、`before_state`、`after_state`、`details`、`reason`
- [x] `tests/business/test_passport_timeline.py` 断言 timeline 包含 `audit_event` 类型与完整字段

## M5 - 前端接线

- [x] `frontend/src/components/Layout.tsx`：控制塔导航 roles 改为 `["pi", "lead", "executor"]`
- [x] `frontend/src/App.tsx`：`/` 路由 RoleRoute 改为 `["pi", "lead", "executor", "system"]`；HOME_BY_ROLE 中 lead/executor 改为 `"/"`
- [x] `frontend/src/screens/TowerScreen.tsx`：兼容 `type=result` 的 needs_action；异常队列仅 PI 显示
- [x] `frontend/src/screens/AuditScreen.tsx`：`canReview = user.role in [pi, lead, executor, system]`
- [x] `frontend/src/screens/PassportScreen.tsx`：渲染 `audit_event` 时间线条目，展示 action/actor/before/after/details
- [x] `frontend/src/i18n/labels.ts`：新增 `audit_event` 对象类型与 `audit_action` 标签映射
- [x] `frontend/src/types/index.ts`：`TimelineEvent` 增加 `action?`、`target_type?`、`target_id?`、`before_state?`、`after_state?`、`details?`、`reason?` 字段；`NeedsAction` 增加 `route?`
- [x] `frontend && npm run build` 通过

## M6 - 校验与归档

- [x] `openspec validate extend-action-audit-permissions-and-trail` 通过
- [x] `conda run -n labmemory pytest -q` 全绿（161 项）
- [x] `openspec archive extend-action-audit-permissions-and-trail --yes` 归档
