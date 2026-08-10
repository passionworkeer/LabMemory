# platform-permissions Specification

## ADDED Requirements

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
- executor：查看授权实验、填写实际参数和结果
- lead：复核候选、批准任务、处理阻断
- pi：管理项目范围、审核关键版本、查看控制塔
- algorithmic：查看预测偏差、提交模型复盘
- readonly：检索授权知识和证据

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
