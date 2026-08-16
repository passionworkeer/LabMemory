# Tasks: harden-deployment-and-perf

## 1. 代码：QA 会话列表 N+1 修复

- [x] 1.1 `labmemory-platform/app/api/qa.py` `list_sessions` 改为单条 `GROUP BY session_id` 聚合取 `message_count`
- [x] 1.2 本地 pytest 全量回归（重点 QA 会话相关用例），确认响应结构不变
  （36 用例 33 过；3 个失败为改动前已存在的本地无 LLM key 意图降级问题，stash 复跑证实与本次无关；
  另做端到端验证：两轮问答 → message_count=4 与详情一致）

## 2. 服务器：nginx 安全头与遗留清理

- [x] 2.1 补 `X-Content-Type-Options: nosniff` / `X-Frame-Options: SAMEORIGIN` / `Content-Security-Policy: frame-ancestors 'self'`（含静态资源 location——nginx add_header 继承规则需显式重申）
- [x] 2.2 删除 `/api/scan` 遗留 location、修正 Next.js 旧注释、`client_max_body_size` 50m→5m、移除藏头不补的 proxy_hide_header 两类行
- [x] 2.3 `nginx -t` 校验后 reload；公网 curl 验证三头到位（首页与 /assets/*.js 均已携带）

## 3. 服务器：systemd 进程监督

- [x] 3.1 编写 `/etc/systemd/system/labmemory-platform.service`（Restart=always, RestartSec=3, journald 日志）
- [x] 3.2 停 nohup 进程 → systemd 拉起 → `kill -9` 演练自动恢复 → `/health` 200（演练通过：5 秒内重启）
- [x] 3.3 移除 crontab `@reboot` 行（platform.log 保留供排查，新日志走 journald）
- [x] 3.4 清理挂起的 pty/sudo 僵尸进程（PID 338880/338881，已 kill，复检 0 残留）

## 4. 服务器：SQLite 每日备份

- [x] 4.1 编写 `~/labmemory/backup_db.sh`（Python stdlib 在线 backup API + 日期后缀 + integrity_check + 保留 7 份）
- [x] 4.2 cron 每日 03:30 调度；手工跑一次验证备份文件落盘可打开（4.6M，integrity ok）

## 5. 部署与回归

- [x] 5.1 同步 qa.py 改动到服务器并重启服务（qa.py.bak.20260816 留档；systemd 切换时一并生效）
- [x] 5.2 公网全量回归：/health 200、/ 200、/docs 404、登录 200、会话列表 200（message_count 正确）、/api/v1 无鉴权 403、/mcp/sse 无 token 403 / 带 token 200
- [x] 5.3 `openspec validate harden-deployment-and-perf` → archive → 中文 git commit
