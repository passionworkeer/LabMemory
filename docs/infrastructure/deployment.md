# 部署 checklist

> 从代码到生产，分**部署前 / 部署中 / 部署后**三段。每段都是 binary checklist，所有项勾完才能算"部署完成"。

---

## 0. 部署拓扑

```
┌──────────────────────────────────────────────────────────────┐
│ 阿里云 Ubuntu-lrtz (<SERVER_IP>, Ubuntu 24.04)             │
│                                                              │
│  ┌─────────────────────────┐    ┌──────────────────────────┐ │
│  │ labmemory-platform      │    │ feishu-orchestrator     │ │
│  │ FastAPI :8081           │    │ webhook_server :8080    │ │
│  │ /home/admin/labmemory/  │    │ （当前未拉起）           │ │
│  │   labmemory-platform/   │    │                          │ │
│  │ SQLite → ./data/*.db    │    │ RUN_MODE=mock 默认       │ │
│  └─────────────────────────┘    └──────────────────────────┘ │
│           ▲                                ▲                  │
│           │                                │                  │
│  ┌────────┴────────────────────────────────┴──────────────┐  │
│  │ nginx :80/:443                                          │  │
│  │ server: <your-domain.com> → reverse_proxy :8081             │  │
│  │         + 飞书事件 webhook → :8080                       │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

详见 [`servers.md`](servers.md)。

---

## 1. 部署前 checklist

### 1.1 本地准备
- [ ] `git status` clean，所有变更已 commit
- [ ] `git log origin/main..HEAD` 为空（无未推送提交）
- [ ] `.env` 用 `python-dotenv` 校验过：`python -c "import dotenv; dotenv.dotenv_values('.env')"` 无错
- [ ] 前端构建产物最新：`cd labmemory-platform/frontend && npm run build`
- [ ] 测试全绿：`cd labmemory-platform && pytest -q`
- [ ] 跨侧集成测试：`bash scripts/cross_side_check.sh`（5/5）

### 1.2 服务器准备
- [ ] SSH 可达：`ssh admin@<SERVER_IP> 'echo OK'`
- [ ] 磁盘 / 内存有富余（>30% 磁盘可用，>500 MiB 内存可用）
- [ ] 当前服务状态已知（看 [`servers.md`](servers.md) §4）
- [ ] 备份策略就位（[`runbook.md`](../operations/runbook.md) §1）
- [ ] 服务器有 `.git/`（**当前没有**，见 [`servers.md`](servers.md) §6.3）

### 1.3 配置准备
- [ ] `labmemory-platform/.env`：
  - [ ] `PLATFORM_API_KEY` ≥ 32 字节随机（与编排器侧同步）
  - [ ] `JWT_SECRET` ≥ 32 字节随机
  - [ ] `DATABASE_URL` 已切换（如需 PG：`postgresql://...`）
  - [ ] `MCP_ENABLED=true`
  - [ ] `AILY_WEBHOOK_BASE_URL` 指向飞书侧 webhook
  - [ ] `AILY_WEBHOOK_SECRET` 与飞书侧一致
- [ ] `feishu-orchestrator/.../.env`：
  - [ ] `RUN_MODE=real`（生产）/`mock`（演示）
  - [ ] `PLATFORM_API_KEY` 与平台一致
  - [ ] `PLATFORM_BASE_URL` 指向平台
  - [ ] `LARK_CLI_BIN` 已安装并 `lark-cli auth login` 完成

### 1.4 网络 / 安全
- [ ] Aily 出口 IP 白名单（`203.166.190.0/24`、`203.166.191.0/24`，定期核对飞书官方文档）
- [ ] `/mcp/sse` 端点能 curl 出 200 OK（带 `PLATFORM_API_KEY`）
- [ ] SSL 证书就绪（Let's Encrypt 或企业 CA）
- [ ] `/etc/letsencrypt/live/<your-domain.com>/` admin 可读（**当前有 bug**，见 [`servers.md`](servers.md) §6.1）

---

## 2. 部署中 checklist

### 2.1 同步代码
```bash
# 推荐：服务器加 .git，配置 deploy key 后走 git pull
ssh admin@<SERVER_IP>
cd /home/admin/labmemory
git fetch origin && git reset --hard origin/main   # 强同步（仅小项目适合）

# 或：本地 rsync
rsync -avz --exclude='.git' --exclude='*.pyc' --exclude='__pycache__' \
    -e ssh ./ admin@<SERVER_IP>:/home/admin/labmemory/
```

### 2.2 更新平台依赖
```bash
ssh admin@<SERVER_IP>
cd /home/admin/labmemory
source .venv/bin/activate
pip install -r labmemory-platform/requirements.txt
cd labmemory-platform/frontend && npm ci && npm run build
```

### 2.3 重启服务
```bash
sudo systemctl restart labmemory-platform
sudo nginx -t && sudo systemctl reload nginx

# 检查
sudo systemctl status labmemory-platform
curl -fsS http://127.0.0.1:8081/health
```

### 2.4 飞书侧（real 模式才需要）
```bash
cd /home/admin/labmemory/feishu-orchestrator/feishu-orchestrator
source ../../.venv/bin/activate
# 用 pm2 或 systemd 拉起 webhook_server
pm2 start "python -m core.webhook_server" --name feishu-orchestrator
pm2 save

curl -fsS http://127.0.0.1:8080/health
```

---

## 3. 部署后 checklist（必须 100% 通过）

### 3.1 健康
- [ ] `curl -fsS http://127.0.0.1:8081/health` → `{"status":"ok"}`
- [ ] `curl -fsS http://127.0.0.1:8081/docs` → Swagger UI 200
- [ ] `curl -fsS http://127.0.0.1:8081/mcp/manifest` → 10 个工具清单
- [ ] `systemctl status labmemory-platform` → active (running)
- [ ] `journalctl -u labmemory-platform -n 50 --no-pager` → 无 ERROR

### 3.2 端到端冒烟
- [ ] 登录：`curl -X POST http://127.0.0.1:8081/api/v1/auth/login -d '{"username":"admin","password":"..."}'`
- [ ] 注入演示数据：`python -m scripts.seed_demo`（仅首次或重置场景）
- [ ] 推 4 个演示会议：`python -m scripts.mock_feishu_push demo`
- [ ] 完整 E2E：`python -m scripts.e2e_test`（14 步全绿）

### 3.3 反向代理
- [ ] `curl -fsS https://<your-domain.com>/health` → 200（**当前 443 证书加载失败**，需先修）
- [ ] `curl -fsS https://<your-domain.com>/mcp/manifest` → 200
- [ ] `curl -fsS "https://<your-domain.com>/mcp/sse?token=$PLATFORM_API_KEY"` → SSE 建立

### 3.4 备份
- [ ] `ls /home/admin/labmemory/backups/` 至少有最近一次备份
- [ ] 备份 cron 在跑：`systemctl list-timers | grep backup` 或 `crontab -l | grep backup_db.sh`

### 3.5 监控 / 巡检
- [ ] 看 [`servers.md`](servers.md) §7 的"最近一次体检"清单，全部勾选

---

## 4. 回滚 checklist（部署出问题）

按**时间倒序**逐项回退：

1. **服务层**：`sudo systemctl restart labmemory-platform` 重启回上次稳定 commit（先 `git checkout <stable-tag>`）
2. **代码层**：`cd /home/admin/labmemory && git reset --hard <stable-commit>`
3. **数据层**：从备份恢复（见 [`runbook.md`](../operations/runbook.md) §3）
4. **配置层**：恢复 `.env.bak.YYYYMMDD-HHMMSS`
5. **网络层**：`sudo systemctl reload nginx`（如果只动了 nginx）

**验证恢复**：
- [ ] §3.1 / §3.2 全部通过
- [ ] 老用户数据无丢失（`sqlite3 labmemory.db "SELECT COUNT(*) FROM users"` 与上次健康数一致）

---

## 5. 部署审计日志

每次部署后，**至少记录**：

| 项 | 例 |
|---|---|
| 时间 | 2026-09-05 16:00 |
| 部署人 | admin |
| commit | `5950c12` |
| 变更类型 | 服务端代码 / 前端构建 / 配置 / 证书 |
| 回滚路径 | `git reset --hard cb7e87b` |
| 健康检查 | ✅ 全部通过 / ❌ [哪项] |

---

## 6. 关联文档

- [`servers.md`](servers.md) — 服务器档案（现状、问题）
- [`../operations/runbook.md`](../operations/runbook.md) — 备份 / 健康 / 应急
- [`../../INTEGRATION.md`](../../INTEGRATION.md) — 启动命令、配置项详解
- [`../../labmemory-platform/README.md`](../../labmemory-platform/README.md) — 平台目录结构、环境要求
- [`../../labmemory-platform/deploy/README.md`](../../labmemory-platform/deploy/README.md) — Nginx / Cloudflare Tunnel 配置
- [`../../feishu-orchestrator/feishu-orchestrator/DEPLOYMENT.md`](../../feishu-orchestrator/feishu-orchestrator/DEPLOYMENT.md) — 飞书 CLI、Real/Mock 模式