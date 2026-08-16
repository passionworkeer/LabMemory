# Proposal: harden-deployment-and-perf — 部署加固与查询性能优化

## Why

赛前全量体检（2026-08-16，服务器 <SERVER_IP> 实测）发现部署层四处短板：

1. **安全响应头缺失**：公网响应仅有 HSTS + Referrer-Policy；`X-Content-Type-Options`、
   `X-Frame-Options` 被 nginx `proxy_hide_header`（旧项目遗留）藏掉且未补——站点可被
   MIME 嗅探与 iframe 嵌套。
2. **进程无监督**：平台以 `@reboot` crontab + nohup 拉起，进程崩溃后**不会自动重启**
   （演示日单点风险）；`platform.log` 无轮转、无限增长。
3. **数据无备份**：4.6MB SQLite 演示库无任何备份，误删即丢。
4. **会话列表 N+1**：`GET /api/qa/sessions` 对每个会话单独 COUNT 一次（20 会话 = 21 条
   SQL），demo 规模可忍，数据增长后线性恶化。

另有卫生问题：nginx 配置遗留上一项目（Attrax/Next.js）的 `/api/scan` location 与注释、
`client_max_body_size 50m` 对 JSON API 过宽；服务器上有 Aug15 挂起的 pty 僵尸进程。

## What Changes

- **nginx**：补 `X-Content-Type-Options: nosniff`、`X-Frame-Options: SAMEORIGIN`、
  `Content-Security-Policy: frame-ancestors 'self'`；删除 `/api/scan` 遗留 location 与
  旧注释；`client_max_body_size` 50m → 5m（编排器侧入站本就限 1MB）。
- **进程监督**：新增 systemd 服务 `labmemory-platform.service`（Restart=always,
  RestartSec=3），替代 crontab `@reboot`；日志收归 journald 自动轮转。
- **备份**：新增每日 03:30 cron `sqlite3 <db> ".backup ..."` 到 `~/backups/labmemory/`，
  保留最近 7 份。
- **性能**：`qa.py list_sessions` 的逐会话 COUNT 改为单条 `GROUP BY` 聚合查询，
  响应结构与语义完全不变。
- **清理**：kill 服务器挂起的 pty/sudo 僵尸进程（PID 338880/338881）。

## Impact

- 影响规格：`runtime-configuration`（ADDED 3 条部署运维需求）、`decision-qa`
  （MODIFIED 会话生命周期管理——补会话列表聚合查询的性能约束，接口语义不变）。
- 不改动任何 API 契约、状态机、闸门规则；`contracts/` 不变。
- 兼容性：纯加固与性能优化，前端无感知；若 systemd 服务异常可回退原
  `start_platform.sh` + crontab 路径。
