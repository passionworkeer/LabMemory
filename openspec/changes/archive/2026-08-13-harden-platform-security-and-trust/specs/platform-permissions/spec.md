## MODIFIED Requirements

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

## ADDED Requirements

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
