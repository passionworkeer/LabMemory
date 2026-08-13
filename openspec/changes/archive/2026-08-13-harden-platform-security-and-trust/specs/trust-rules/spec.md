## ADDED Requirements

### Requirement: 并发发布串行化
系统 SHALL 在主张发布为 `current`（`confirm_review` 与 `/api/v1/card/callback` 的 approve 路径）的临界区——读取实验当前 current 主张、将其置 `superseded`、写入新 current——按实验串行化，MUST NOT 允许两个并发发布在同一实验上各自基于陈旧读取创建多条 current。实现 SHALL 采用按实验的排他写锁覆盖「读旧 current 至事务提交」整段（单进程内线程锁；Postgres 下叠加 `SELECT ... FOR UPDATE` 锁实验行）。锁粒度 MUST 为实验级，MUST NOT 阻塞不同实验的并发发布。

#### Scenario: 并发 confirm 不产生双 current
- GIVEN 实验 EXP-001 已有一条 current 主张 C_old，两个 confirm_review 请求近乎同时到达
- WHEN 两者同时进入 supersede 临界区
- THEN 系统 SHALL 串行化处理：后到者 SHALL 读到先到者写入后的状态，最终实验仅保留一条 current 主张，MUST NOT 同时存在两条 current

#### Scenario: 不同实验并发不互相阻塞
- GIVEN 两个 confirm_review 请求分别针对实验 EXP-001 与 EXP-002
- WHEN 两者并发执行
- THEN 两者 SHALL 不因彼此的写锁而阻塞，均可正常完成
