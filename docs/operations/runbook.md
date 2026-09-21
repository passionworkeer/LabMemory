# 运维 Runbook (Operations Runbook)

> 本文档为生产环境日常运维标准操作流程（SOP）：数据备份、健康检查、故障应急排查与 SSL 证书维护。
> 配套文档：[`../infrastructure/servers.example.md`](../infrastructure/servers.example.md)（服务器参考规划）、[`../infrastructure/deployment.md`](../infrastructure/deployment.md)（部署 checklist）。

---

## 1. 备份策略与验证

### 1.1 数据库每日在线备份
平台使用 SQLite 配合 Python 标准库的 `sqlite3.backup()` 在线热备 API，备份过程不锁库、不影响线上读写。

备份脚本：`deploy/backup_db.sh`

配置每日定时任务（以每天 03:30 为例）：
```bash
# 编辑 crontab
crontab -e

# 添加如下定时调度
30 3 * * * /home/admin/labmemory/deploy/backup_db.sh >> /home/admin/labmemory/backup.log 2>&1
```

### 1.2 验证定时备份正常运行
```bash
ssh admin@<SERVER_IP>

# 检查 crontab 状态
crontab -l | grep backup_db.sh

# 查看备份日志，确认有成功记录
tail -20 /home/admin/labmemory/backup.log

# 检查归档目录（默认轮转保留最近 7 份）
ls -l /home/admin/labmemory/backups/
```

### 1.3 手动触发备份
```bash
ssh admin@<SERVER_IP>
bash /home/admin/labmemory/deploy/backup_db.sh

# 检查最新生成的快照
ls -lt /home/admin/labmemory/backups/ | head -5
```

---

## 2. 健康检查与监控

### 2.1 本地健康探针
```bash
# 1. 检查 HTTP 健康状态
curl -fsS http://127.0.0.1:8081/health

# 2. 检查工具列表响应
curl -fsS http://127.0.0.1:8081/mcp/manifest

# 3. 检查系统服务运行状态
sudo systemctl status labmemory-platform
```

### 2.2 公网与反代健康检查
```bash
# 检查公网 HTTPS 入口响应
curl -fsS https://<your-domain.com>/health

# 检查 SSE 流式长连接握手
curl -N -H "Authorization: Bearer <PLATFORM_API_KEY>" https://<your-domain.com>/mcp/sse
```

---

## 3. 故障应急排障 SOP

### 3.1 平台服务无响应或卡死（优雅重启与强制恢复）
```bash
ssh admin@<SERVER_IP>

# 1. 尝试优雅重启
sudo systemctl restart labmemory-platform

# 2. 若超时未退出，检查残留进程
ps -ef | grep "uvicorn.*8081" | grep -v grep

# 3. 强制终止残留
pkill -f "uvicorn.*8081"
sleep 2

# 4. 重新拉起并验证健康
sudo systemctl start labmemory-platform
curl -fsS http://127.0.0.1:8081/health
```

### 3.2 Nginx 502 Bad Gateway
```bash
ssh admin@<SERVER_IP>

# 1. 检查 Nginx 配置文件语法
sudo nginx -t

# 2. 确认平台本地 8081 端口是否在监听
curl -fsS http://127.0.0.1:8081/health

# 3. 查看平台最新日志
sudo journalctl -u labmemory-platform -n 50 --no-pager

# 4. 平滑重载 Nginx
sudo systemctl reload nginx
```

### 3.3 SQLite "database is locked" 异常
```bash
ssh admin@<SERVER_IP>

# 1. 停止应用服务以释放锁
sudo systemctl stop labmemory-platform
sleep 10

# 2. 查看是否有残留进程占用数据库文件
sudo lsof /home/admin/labmemory/labmemory-platform/data/labmemory.db

# 3. 确认文件占用已释放后重启
sudo systemctl start labmemory-platform
```

### 3.4 磁盘空间告警清理
```bash
ssh admin@<SERVER_IP>

# 检查磁盘挂载利用率
df -h /

# 清理 systemd 超过 7 天的历史日志
sudo journalctl --vacuum-time=7d

# 清理多余的临时备份文件
ls -t /home/admin/labmemory/backups/*.db | tail -n +5 | xargs -r rm -f
```

---

## 4. SSL 证书维护 (Let's Encrypt / Certbot)

### 4.1 证书有效期检查
```bash
sudo certbot certificates
```

### 4.2 手动测试与强制续期
```bash
# 模拟续期演练
sudo certbot renew --dry-run

# 执行实际续期并重载 Nginx
sudo certbot renew --nginx
sudo systemctl reload nginx
```

---

## 5. 安全访问与 SSH 访问控制

### 5.1 生产访问建议
- 禁用 root 远程密码登录，仅允许 SSH 密钥认证。
- 建议通过 `~/.ssh/config` 配置专用 Host 别名：

```ssh-config
Host labmemory-prod
    HostName <SERVER_IP>
    User admin
    IdentityFile ~/.ssh/<your_private_key>
    ServerAliveInterval 60
```

---

## 6. 关联文档

- [`../infrastructure/servers.example.md`](../infrastructure/servers.example.md) — 生产规划参考
- [`../infrastructure/deployment.md`](../infrastructure/deployment.md) — 完整部署 checklist
- [`../../INTEGRATION.md`](../../INTEGRATION.md) — 系统配置与运行模式详解