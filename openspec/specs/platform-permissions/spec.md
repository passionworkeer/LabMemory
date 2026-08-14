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
系统 SHALL 在启动时检测 `JWT_SECRET` 与 `PLATFORM_API_KEY` 是否为代码默认值。当 `APP_ENV=production` 且任一密钥为默认值时，系统 MUST 拒绝启动并报错（防止生产以弱密钥运行，存在伪造/越权风险）。其余环境（`APP_ENV` 默认 `development`）下密钥为默认值时 SHALL 输出显眼 warning 但正常启动（保留 dev/test 可运行性）。

#### Scenario: 生产环境默认密钥拒绝启动
- GIVEN `APP_ENV=production` 且 `JWT_SECRET` 仍为默认值 `dev-jwt-secret-please-rotate`
- WHEN 平台启动
- THEN 系统 SHALL 抛错拒绝启动，MUST NOT 以默认密钥进入服务态

#### Scenario: 默认密钥启动告警
- GIVEN `APP_ENV` 未设置或为 `development`，`JWT_SECRET` 为默认值
- WHEN 平台启动
- THEN 日志 SHALL 输出「JWT_SECRET 为默认值，生产必须覆盖」warning，服务正常启动

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

### Requirement: 实现路径与权限模型对齐说明
系统 SHALL 以 `/api/...` 为 API 路径基线（如 `/api/meetings`、`/api/tasks/{id}`、`/api/control-tower`、`/api/experiments/{id}/passport`），权限 MUST 通过角色依赖（`admin`/`pi`/`lead`/`executor`）+ `ExperimentMember` 成员关系强制。早期规格中出现的 `/web/...` 路径与命名权限为未落地的前瞻设计；以本对齐说明为准，`/web/...` MUST NOT 作为实现契约。

#### Scenario: 路径以 /api 为准
- GIVEN 任意客户端访问平台
- WHEN 调用任务审计/控制塔/护照等接口
- THEN 命中路径 SHALL 为 `/api/...`（非 `/web/...`），权限由角色 + 成员关系判定

### Requirement: 实验管理操作限项目所有者
系统 SHALL 对实验管理接口（`POST /api/experiments`、`GET /api/experiments/{id}`、`POST /api/experiments/{id}/members`）强制：操作者必须是该实验所属项目的 PI（`Project.pi_user_id == user.id`）或 `admin`，否则 MUST 返回 403。非项目所有者的 PI MUST NOT 在他人项目下创建实验、读取实验详情或增删成员。

#### Scenario: PI 不能在他人项目下建实验
- GIVEN 用户 u_pi_A 是项目 Alpha 的 PI，项目 Beta 属于另一位 PI
- WHEN u_pi_A 调用 `POST /api/experiments` 携带 `project_id=Beta`
- THEN 系统 SHALL 返回 403，MUST NOT 创建实验

#### Scenario: PI 不能改他人实验的成员
- GIVEN 用户 u_pi_A 是项目 Alpha 的 PI，EXP-B 属于项目 Beta（非 u_pi_A 所有）
- WHEN u_pi_A 调用 `POST /api/experiments/EXP-B/members`
- THEN 系统 SHALL 返回 403，MUST NOT 修改成员关系

### Requirement: 跨实验读取的全局可见口径

问答检索、会前简报、实验护照三条路由的实验可见范围 MUST 与 `visible_experiment_ids` 同一口径：仅 admin 全局可见；PI 与其他角色按项目归属/实验成员关系可见。上述路由不得对 PI 额外放宽为全局读取。

#### Scenario: 他项目 PI 不可经问答读取

- GIVEN PI 甲是项目 P1 所有者，乙项目 P2 的实验 E2 与甲无成员关系
- WHEN 甲向可信问答提问 E2 相关参数
- THEN E2 的切片 SHALL 不在甲的检索候选集中，命中不足时按拒答契约返回

### Requirement: 登录失败限速

登录接口 SHALL 对同一「用户名 + 客户端 IP」组合做失败限速：连续失败达到阈值（默认 5 次）后锁定该组合一段时间（默认 15 分钟），锁定期内返回 429。进程重启可重置（受控试点可接受）。

#### Scenario: 暴力破解被锁定

- GIVEN 攻击者对 admin 账号从同一 IP 连续提交 5 次错误密码
- WHEN 第 6 次尝试到达
- THEN 响应 SHALL 为 429 且提示稍后重试，正确密码在锁定期内也不放行

