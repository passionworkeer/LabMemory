## ADDED Requirements

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
