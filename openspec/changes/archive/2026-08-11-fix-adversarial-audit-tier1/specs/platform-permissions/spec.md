# platform-permissions Specification Delta

## ADDED Requirements

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
