# Design: 扩展行动审计权限、待处理通知与护照时间线

## 决策

### 1. 新增 `operate_action_audit` 权限项而非扩展 `review_candidate` / `handle_block`

候选补充口径：直接复用 `review_candidate` 会让 executor 顺带获得 `POST /web/inbox/{id}/reject` 等候选复核权限，破坏「执行人不复核候选」的产品红线。直接复用 `handle_block` 会让 executor 获得处理阻断的语义，但 `handle_block` 当前未在任何端点单独使用，含义模糊。

新增独立权限 `operate_action_audit` 更明确：它专指「在行动审计页面对任务执行五类检查与修正动作」，与候选复核（review_candidate）、版本批准（approve_version）、知识确认（confirm_knowledge_state）保持正交。executor / lead / pi 都拥有此权限，使执行人可在 lead 不在场时独立完成行动审计闭环。

### 2. 控制塔开放给 lead/executor 而非新增 `/web/dashboard` 端点

候选补充口径：新增端点会带来前端路由、TypeScript 类型、缓存 key 的连锁改动，且 TowerScreen 已经聚合 KPI/needs_action/anomalies 三段结构。直接扩展 `/web/control-tower` 让 lead/executor 访问，按角色返回不同 needs_action，是最小变更：

- 权限矩阵中给 lead/executor 增加 `view_control_tower`。
- KPI 对所有角色返回（数字按项目成员过滤，executor 看到的是自己项目的全局数字，符合「项目成员隔离」）。
- needs_action 按角色与 owner 过滤：executor 只看自己的待办；lead/pi 看项目内全部。
- anomalies 队列只对 PI 返回（执行人无重试权限，看到异常也无意义），其他角色返回空数组。

### 3. 护照时间线聚合 AuditEvent 而非新增 timeline 表

候选补充口径：可以考虑新增 `experiment_timeline_events` 表统一存储所有时间线条目。但 AuditEvent 已经覆盖所有正式状态变更，且 spec 已要求「不可篡改、可追溯」。直接复用 AuditEvent 即可，不必引入冗余表。

实现方式：在 `get_passport` 内按 (target_type, target_id) 元组集合查询 AuditEvent，每条 AuditEvent 转为 timeline entry。`target_type` 已覆盖 candidate / claim / decision / task / task_draft / result / failure_boundary / parameter_version / knowledge_card / integration_action，正好对应护照关联对象。

去重：同一 (target_type, target_id) 可能有多条 AuditEvent（如 task 经历 created -> audit_executed -> started -> ...），全部保留，按 `occurred_at` 排序。

## 风险与边界

- **权限扩展影响**：executor 现在能触发审计和一键修正，但行动审计服务 `run_action_audit` 不依赖角色，五类检查逻辑独立。一键修正只替换为同 claim 当前 active 版本，不会让 executor 创建「自定义」版本。安全。
- **控制塔开放给 executor**：executor 能看到项目级 KPI（待复核候选数等），这是合理的项目成员可见性。`accessible_project_ids` 已按 ProjectMember 过滤，跨项目不泄露。
- **护照时间线膨胀**：长流程实验可能产生数十条 AuditEvent。timeline 已按时间排序，前端展示为竖直列表，每条 1-2 行，UI 可承载。如未来需要分页，可在前端做无限滚动，后端不必改。
- **AuditEvent.target_id 与业务对象 ID 一致性**：所有 write_audit_event 调用均使用业务编号（如 task_id="T001"），与 passport 中查询的对象 ID 一致，无需 ID 映射。
- **不修改 contracts 与规格源真相**：本变更不涉及 `feishu-orchestrator/` 与 `app/contracts/`，也不修改已归档的 specs（只增改活跃 change 内的 delta）。

## 实现顺序

1. 后端权限矩阵与端点：`permissions.py` -> `audit.py` 端点
2. 控制塔扩展：`control_tower.py` 端点
3. 护照扩展：`passport.py` 服务
4. 前端：`Layout.tsx` / `App.tsx` -> `TowerScreen.tsx` -> `AuditScreen.tsx` -> `PassportScreen.tsx` -> `i18n/labels.ts` / `types/index.ts`
5. 测试：新增 executor 行动审计权限测试 + 控制塔按角色测试 + 护照 AuditEvent 测试
6. `openspec validate` -> `pytest` -> `openspec archive`
