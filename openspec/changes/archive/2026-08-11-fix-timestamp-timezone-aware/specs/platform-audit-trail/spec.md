## ADDED Requirements

### Requirement: 时间戳时区规范
系统 SHALL 以 timezone-aware UTC 写入所有 datetime 字段（含 AuditEvent.created_at 及业务时间戳 reviewed_at、audited_at、approved_at、published_at、effective_at、compiled_at、captured_at、last_activity_at、timeline.timestamp、created_at、updated_at），并在 API 响应中序列化为带 UTC 时区后缀（`+00:00` 或 `Z`）的 ISO 8601 字符串。系统 MUST NOT 使用 `datetime.utcnow()` 等 naive datetime 写入方式生成业务时间戳。当 DB 读回的 datetime 因存储层剥离 tzinfo 而为 naive 时，序列化层 SHALL 默认按 UTC 处理并补全时区后缀。

#### Scenario: 新写入的审计事件 API 响应带时区后缀
- GIVEN 负责人确认候选 CAND-001 触发状态变更
- WHEN 系统写入 AuditEvent 并通过 API 返回
- THEN 响应中 `created_at` SHALL 形如 `2026-08-11T07:21:21.226220Z` 或 `2026-08-11T07:21:21.226220+00:00`，MUST NOT 为 `2026-08-11T07:21:21.226220`（无时区后缀）

#### Scenario: 前端按本地时区正确显示
- GIVEN 浏览器位于 Asia/Shanghai (+0800) 时区，后端返回 `2026-08-11T07:21:21.226220Z`
- WHEN 前端执行 `new Date("2026-08-11T07:21:21.226220Z").toLocaleString()`
- THEN 显示 SHALL 为 `2026/8/11 15:21:21`（本地时区），MUST NOT 显示为 `2026/8/11 07:21:21`（UTC 原值）

#### Scenario: 近 24h 截止计算无时区偏移
- GIVEN 控制塔查询"近 24h 发布"结果列表，当前服务器本地时间为 2026-08-11 15:00 CST
- WHEN 系统计算 24h 截止时间
- THEN cutoff SHALL 等于 2026-08-10 07:00 UTC（即 2026-08-10 15:00 CST），MUST NOT 因 naive datetime 偏移导致 cutoff 落在 2026-08-09 23:00 CST（实际窗口扩大为 32h）

#### Scenario: TimestampMixin 默认值使用 timezone-aware UTC
- GIVEN 任意模型继承 TimestampMixin 并新建记录
- WHEN SQLAlchemy 触发 `created_at` 默认值
- THEN 默认值 SHALL 由 `datetime.now(timezone.utc)` 产生（timezone-aware UTC），MUST NOT 由 `datetime.utcnow()` 产生（naive）

#### Scenario: 历史 naive 数据在 API 响应中补全时区后缀
- GIVEN DB 中存在存量 naive datetime 记录（本次变更前写入，无 tzinfo）
- WHEN API 返回该记录的 datetime 字段
- THEN 序列化层 SHALL 将 naive datetime 视为 UTC 并补全时区后缀（`Z` 或 `+00:00`），前端展示 SHALL 与新数据一致（按本地时区正确显示），MUST NOT 因存量数据无 tzinfo 而显示为早 8 小时
