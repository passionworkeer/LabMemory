## ADDED Requirements

### Requirement: HTTPS 安全响应头基线

生产入口（nginx）MUST 对全部响应附加以下安全响应头：

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`（等价 CSP `frame-ancestors 'self'`）
- `Strict-Transport-Security`（已有，保持）

配置 MUST NOT 再从后端响应中隐藏安全头而不补齐等价头（清理旧项目遗留的
`proxy_hide_header x-frame-options / x-content-type-options` 语义）。

#### Scenario: 公网响应携带完整安全头

- GIVEN 平台经 https://<your-domain.com> 对外提供服务
- WHEN 客户端 GET `/`（任意路径）
- THEN 响应头 SHALL 同时包含 `X-Content-Type-Options: nosniff` 与 `X-Frame-Options: SAMEORIGIN`

### Requirement: 平台进程监督与自动恢复

生产环境平台进程 MUST 由 systemd 托管（`labmemory-platform.service`），配置
`Restart=always` 与 `RestartSec<=5s`；进程崩溃后 SHALL 自动拉起，无需人工干预。
日志 SHALL 收归 journald（自动轮转），MUST NOT 依赖无限增长的裸 log 文件。

#### Scenario: 进程崩溃自动重启

- GIVEN systemd 服务运行中（MainPID=P1）
- WHEN kill -9 P1
- THEN systemd SHALL 在 5 秒内重新拉起进程，`/health` 恢复 200

### Requirement: SQLite 数据库每日备份

生产环境 MUST 配置每日离线安全备份：cron 定时执行 `sqlite3 <db> ".backup <目标>"` 到
独立目录（`~/backups/labmemory/`），保留最近 7 份，超期自动清理。备份 MUST 使用
sqlite 在线备份 API（`.backup`），MUST NOT 直接 cp 活库文件。

#### Scenario: 每日备份落盘且轮转

- GIVEN 备份 cron 已配置
- WHEN 每日备份时刻到达
- THEN `~/backups/labmemory/` 出现当日带日期后缀的备份文件，且目录内文件数不超过 7
