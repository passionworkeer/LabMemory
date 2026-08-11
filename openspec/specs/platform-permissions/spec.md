# platform-permissions Specification

## Purpose
TBD - created by archiving change add-labmemory-platform-implementation. Update Purpose after archive.
## Requirements
### Requirement: 五角色权限模型
系统 SHALL 定义五类角色：实验执行人（executor）、实验负责人（lead）、项目负责人（pi）、算法人员（algorithmic）、只读成员（readonly）；业务权限由平台角色与项目成员关系共同决定，MUST NOT 仅依赖飞书 user_id。

#### Scenario: 执行人不能批准参数替代
- GIVEN 用户 u_zhou 角色为 executor 且属于 Alpha 项目
- WHEN u_zhou 调用 `POST /web/versions/{claim_id}/activate`
- THEN 系统 SHALL 返回 403，MUST NOT 修改参数版本状态

### Requirement: 项目成员关系
系统 SHALL 通过 `ProjectMember` 表校验用户对特定项目的访问权限；非项目成员 MUST NOT 访问该项目下的实验、候选、结果。

#### Scenario: 跨项目访问被拒
- GIVEN 用户 u_zhou 是 Alpha 项目成员但不是 Beta 项目成员
- WHEN u_zhou 调用 `GET /web/passport/EXP-SYN-0042`（Beta 项目实验）
- THEN 系统 SHALL 返回 403

### Requirement: 角色与操作映射
系统 SHALL 按下表强制角色权限：
- executor：查看授权实验、操作行动审计、填写实际参数和结果、查看控制塔中属于自己的待处理
- lead：复核候选、操作行动审计、批准任务、处理阻断、查看控制塔
- pi：管理项目范围、审核关键版本、操作行动审计、查看控制塔（含异常队列与重试）
- algorithmic：查看预测偏差、提交模型复盘
- readonly：检索授权知识和证据

系统 SHALL 定义平台权限 `operate_action_audit`，含义为「在行动审计页面执行五类检查与修正动作」，包括触发审计、更新审计上下文、确认重审、一键修正；executor / lead / pi / system 均拥有此权限。

#### Scenario: 执行人可触发行动审计
- GIVEN 用户 u_lin 角色为 executor 且属于项目 Alpha，存在分配给 u_lin 的待审计任务 T001
- WHEN u_lin 调用 `POST /web/tasks/T001/audit`
- THEN 系统 SHALL 返回 200，并执行行动审计写入 AuditEvent

#### Scenario: 执行人可更新审计上下文
- GIVEN 用户 u_lin 角色为 executor 且任务 T001 处于 needs_confirmation
- WHEN u_lin 调用 `PUT /web/tasks/T001/audit-context`
- THEN 系统 SHALL 返回 200，更新 audit_context_json 并触发重新审计

#### Scenario: 执行人可一键修正阻断任务
- GIVEN 用户 u_lin 角色为 executor 且任务 T001 处于 blocked
- WHEN u_lin 调用 `POST /web/tasks/T001/fix`
- THEN 系统 SHALL 返回 200，创建新任务并保留旧任务为 blocked

#### Scenario: 执行人仍不能批准参数版本
- GIVEN 用户 u_lin 角色为 executor
- WHEN u_lin 调用 `POST /web/versions/{claim_id}/activate`
- THEN 系统 SHALL 返回 403，MUST NOT 修改参数版本状态

#### Scenario: 执行人仍不能复核候选
- GIVEN 用户 u_lin 角色为 executor
- WHEN u_lin 调用 `POST /web/inbox/{candidate_id}/review`
- THEN 系统 SHALL 返回 403，required_permission 为 `review_candidate`

#### Scenario: 执行人仍不能确认知识状态
- GIVEN 用户 u_lin 角色为 executor 且提交了结果 RESULT-001
- WHEN u_lin 调用 `POST /web/results/RESULT-001/review`
- THEN 系统 SHALL 返回 403，required_permission 为 `confirm_knowledge_state`

#### Scenario: 算法人员不能修改实验结论
- GIVEN 用户 u_algo 角色为 algorithmic
- WHEN u_algo 调用 `POST /web/results` 提交实验结果
- THEN 系统 SHALL 返回 403

### Requirement: 飞书 user_id 与平台角色解耦
登录可接收飞书 user_id，但业务权限由平台角色决定；所有正式状态变更 MUST 记录操作者、时间、前值、后值、原因。

#### Scenario: user_id 不自动获得权限
- GIVEN 用户首次以飞书 user_id `ou_xxx` 登录
- WHEN 系统签发 JWT
- THEN 系统 SHALL 默认分配 `readonly` 角色，MUST NOT 因 user_id 存在而授予写权限

### Requirement: 默认密钥启动告警
系统 SHALL 在启动时检测 `JWT_SECRET` 与 `PLATFORM_API_KEY` 是否为代码默认值；若为默认值 SHALL 输出显眼 warning（生产部署 MUST 覆盖为强随机值）。系统 MUST NOT 因默认值直接拒绝启动（保留 dev/test 可运行性）。

#### Scenario: 默认密钥启动告警
- GIVEN 部署未覆盖 `JWT_SECRET`（仍为 `dev-jwt-secret-please-rotate`）
- WHEN 平台启动
- THEN 日志 SHALL 输出「JWT_SECRET 为默认值，生产必须覆盖」warning，服务仍正常启动

### Requirement: CORS 白名单与凭据互斥
系统 SHALL 默认 `CORS_ORIGINS` 为本地开发白名单（`http://localhost:5173,http://localhost:8081`）；当来源含 `*` 时 SHALL 强制 `allow_credentials=False` 并 warning，MUST NOT 允许 `*` 与凭据共存。

#### Scenario: 通配源禁带凭据
- GIVEN `CORS_ORIGINS=*`
- WHEN 平台启动
- THEN 系统 SHALL 以 `allow_credentials=False` 挂载 CORS 中间件并 warning

### Requirement: 跨实验读取按成员可见域过滤
系统 SHALL 对列表/详情读接口（`GET /api/meetings`、`/api/meetings/{id}`、`/api/meetings/{id}/chain`、`GET /api/tasks/{id}`、`/api/tasks/{id}/audit/compare`、`GET /api/control-tower`）按角色过滤：`admin`/`pi` 全局可见；`lead`/`executor` MUST 仅可见其 `ExperimentMember` 所属实验的对象。非成员访问他人实验对象 SHALL 返回 403。

#### Scenario: executor 不能读他人实验会议
- GIVEN 用户 u_web 为 executor 且仅属 EXP-001，会议 m_belongsto_exp2 属 EXP-002
- WHEN u_web 请求 `GET /api/meetings/{m_belongsto_exp2}`
- THEN 系统 SHALL 返回 403

### Requirement: reset-demo 仅 admin
系统 SHALL 限制 `POST /reset-demo` 仅 `admin` 可调用；`pi` MUST NOT 能清空他人项目数据。

#### Scenario: PI 不能 reset-demo
- GIVEN 用户 u_pi 角色为 pi
- WHEN u_pi 调用 `POST /reset-demo`
- THEN 系统 SHALL 返回 403

