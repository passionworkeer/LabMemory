# 运维 Runbook

> 日常运维的 SOP：备份、健康检查、故障应急、证书续期、SSH 凭据。
> 配套：[`../infrastructure/servers.md`](../infrastructure/servers.md)（现状）、[`../infrastructure/deployment.md`](../infrastructure/deployment.md)（部署）。

---

## 1. 备份策略

### 1.1 数据库每日在线备份

`/home/admin/labmemory/deploy/backup_db.sh` 由 cron 每日 03:30 触发（2026-09-10 修正过路径，见下）：

> ⚠️ **历史事故**：2026-09-06 ~ 09-10 备份断裂 5 天——方案 B 切到 git 目录后 cron 仍指向旧路径 `/home/admin/labmemory/backup_db.sh`（仓库根），该文件已不存在。9-10 已改指 `deploy/backup_db.sh`（走 `/home/admin/labmemory` 软链，稳定），并补跑当日备份。**教训：巡检必须看 `backup.log` 内容而不只是 cron 行是否存在。**

```bash
# 输出
$ ls /home/admin/labmemory/backups/
labmemory_20260830_033001.db
labmemory_20260831_033001.db
labmemory_20260901_033002.db
labmemory_20260902_033001.db
labmemory_20260903_033002.db
labmemory_20260904_033001.db
labmemory_20260905_033001.db

# 共 7 份，每天一份，文件名带时间戳
```

**关键性质**：
- 用 Python stdlib `sqlite3.backup()` API —— 在线、不锁库、官方推荐方式
- 备份完做 `PRAGMA integrity_check`，损坏自动删
- 自动轮转保留最近 7 份

### 1.2 验证 cron 仍在跑
```bash
ssh admin@<SERVER_IP>
crontab -l | grep backup_db.sh
# 应该看到一行：30 3 * * * /home/admin/labmemory/deploy/backup_db.sh >> /home/admin/labmemory/backup.log 2>&1
tail -5 /home/admin/labmemory/backup.log    # ⚠️ 必须看日志内容，确认没有 not found / 失败
```

如果 cron 行丢了：

```bash
ssh admin@<SERVER_IP>
(crontab -l 2>/dev/null; echo "30 3 * * * /home/admin/labmemory/deploy/backup_db.sh >> /home/admin/labmemory/backup.log 2>&1") | crontab -
```

### 1.3 手动触发备份
```bash
ssh admin@<SERVER_IP>
bash /home/admin/labmemory/deploy/backup_db.sh
# 检查最新一份
ls -la /home/admin/labmemory/backups/ | tail -1
```

---

## 2. 健康检查

### 2.1 快速体检（1 分钟）

```bash
ssh admin@<SERVER_IP> << 'EOF'
echo "=== 平台 ==="
curl -fsS http://127.0.0.1:8081/health || echo "❌ 平台不通"
echo "=== Nginx ==="
sudo nginx -t 2>&1 | tail -3
echo "=== 服务状态 ==="
systemctl is-active labmemory-platform nginx ssh
echo "=== 资源 ==="
df -h / | tail -1
free -h | head -2 | tail -1
echo "=== 平台日志错误 ==="
journalctl -u labmemory-platform -n 100 --no-pager 2>/dev/null | grep -iE "error|exception|traceback" | tail -10
echo "=== 备份新鲜度 ==="
ls -la /home/admin/labmemory/backups/ | tail -2
EOF
```

判定：
- 全部 OK → 健康
- 任意 ❌ → 按 §4 应急

### 2.2 每周深度体检

```bash
ssh admin@<SERVER_IP> << 'EOF'
echo "=== 证书有效期 ==="
echo | openssl s_client -connect 127.0.0.1:443 -servername <your-domain.com> 2>/dev/null | openssl x509 -noout -dates 2>&1
echo "=== 备份完整性 ==="
for f in /home/admin/labmemory/backups/labmemory_*.db; do
  /home/admin/labmemory/.venv/bin/python -c "
import sqlite3, sys
db = sqlite3.connect('$f')
ok = db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print('  ', '$f', '✅' if ok else '❌')
"
done
echo "=== 平台 E2E（可选，会写数据） ==="
cd /home/admin/labmemory/labmemory-platform
/home/admin/labmemory/.venv/bin/python -m scripts.e2e_test 2>&1 | tail -20
EOF
```

---

## 3. 数据恢复

### 3.1 从备份恢复 SQLite

```bash
ssh admin@<SERVER_IP>
sudo systemctl stop labmemory-platform
cp /home/admin/labmemory/labmemory-platform/data/labmemory.db \
   /home/admin/labmemory/labmemory-platform/data/labmemory.db.corrupted.$(date +%s)
cp /home/admin/labmemory/backups/labmemory_YYYYMMDD_HHMMSS.db \
   /home/admin/labmemory/labmemory-platform/data/labmemory.db
chown admin:admin /home/admin/labmemory/labmemory-platform/data/labmemory.db
sudo systemctl start labmemory-platform
curl -fsS http://127.0.0.1:8081/health
```

### 3.2 验证恢复

```bash
ssh admin@<SERVER_IP>
/home/admin/labmemory/.venv/bin/python -c "
import sqlite3
db = sqlite3.connect('/home/admin/labmemory/labmemory-platform/data/labmemory.db')
print('users:', db.execute('SELECT COUNT(*) FROM users').fetchone()[0])
print('experiments:', db.execute('SELECT COUNT(*) FROM experiments').fetchone()[0])
print('meetings:', db.execute('SELECT COUNT(*) FROM meetings').fetchone()[0])
"
```

数据量应与备份前一致（用户数、实验数、会议数）。

---

## 4. 故障应急

### 4.1 平台进程挂了

```bash
ssh admin@<SERVER_IP>
sudo systemctl status labmemory-platform
journalctl -u labmemory-platform -n 50 --no-pager
sudo systemctl restart labmemory-platform
sleep 3
curl -fsS http://127.0.0.1:8081/health
```

如果重启失败，看 journald：
- `ModuleNotFoundError` → `pip install -r labmemory-platform/requirements.txt`
- `Address already in use` → `sudo lsof -i :8081`，找到 PID 杀掉
- 数据库锁 → 看 §4.4

### 4.2 Nginx 502 Bad Gateway

```bash
ssh admin@<SERVER_IP>
sudo nginx -t                                # 语法检查
curl -fsS http://127.0.0.1:8081/health       # 平台通不通
sudo systemctl status labmemory-platform     # 平台服务状态
sudo nginx -s reload                         # 平滑重载
```

### 4.3 HTTPS 证书过期/加载失败

```bash
ssh admin@<SERVER_IP>
sudo nginx -t 2>&1 | grep -i "certificate\|ssl"
# 确认证书文件存在且可读
sudo ls -la /etc/letsencrypt/live/<your-domain.com>/
# 续期（certbot）
sudo certbot renew --nginx --dry-run
sudo certbot renew --nginx
sudo systemctl reload nginx
```

**admin 看不到证书目录**（root-only），用 [`admin_tool.py`](../../deploy/admin_tool.py)：

```bash
ssh admin@<SERVER_IP>
<ROOT_PASSWORD>=xxx python3 /home/admin/labmemory/admin_tool.py 'ls -la /etc/letsencrypt/live/<your-domain.com>/'
```

### 4.4 SQLite "database is locked"

```bash
ssh admin@<SERVER_IP>
sudo systemctl stop labmemory-platform
# 等所有写连接释放（最多 5 分钟）
sleep 30
# 如果还锁：
sudo lsof /home/admin/labmemory/labmemory-platform/data/labmemory.db
# 强制清掉（仅紧急）
sudo fuser -k /home/admin/labmemory/labmemory-platform/data/labmemory.db
sudo systemctl start labmemory-platform
```

### 4.5 磁盘满

```bash
ssh admin@<SERVER_IP>
df -h /
du -sh /home/admin/labmemory/* | sort -h | tail -10
du -sh /var/log/* 2>/dev/null | sort -h | tail -10
# 清理旧日志
sudo journalctl --vacuum-time=7d
# 清理旧备份（脚本自动保留 7 天，手动可更激进）
ls -t /home/admin/labmemory/backups/*.db | tail -n +4 | xargs -r rm
```

### 4.6 平台卡死（重启大法）

```bash
ssh admin@<SERVER_IP>
# 优雅停服
sudo systemctl stop labmemory-platform
# 等待 10 秒
sleep 10
# 检查还有没有残留
ps -ef | grep "uvicorn.*8081" | grep -v grep
# 强制杀
pkill -f "uvicorn.*8081"
sleep 2
# 拉起
sudo systemctl start labmemory-platform
curl -fsS http://127.0.0.1:8081/health
```

---

## 5. SSL 证书续期

**当前状态**：Let's Encrypt 证书在 `/etc/letsencrypt/live/<your-domain.com>/`，有效期 2026-08-20 ~ **2026-11-18**。admin 已可读（2026-09-05 已 chmod o+rX 修复，见 [`../infrastructure/servers.md`](../infrastructure/servers.md) §6.1），`certbot.timer` 自动续期在跑。

### 5.1 自动续期

certbot 一般会装 systemd timer 自动续期。检查：

```bash
ssh admin@<SERVER_IP>
<ROOT_PASSWORD>=xxx python3 /home/admin/labmemory/admin_tool.py 'systemctl list-timers | grep certbot'
```

### 5.2 手动续期（需要 root）

```bash
ssh admin@<SERVER_IP>
<ROOT_PASSWORD>=xxx python3 /home/admin/labmemory/admin_tool.py 'certbot renew --nginx'
<ROOT_PASSWORD>=xxx python3 /home/admin/labmemory/admin_tool.py 'systemctl reload nginx'
```

### 5.3 修复 admin 读证书权限（建议）

```bash
ssh admin@<SERVER_IP>
<ROOT_PASSWORD>=xxx python3 /home/admin/labmemory/admin_tool.py 'chmod -R o+rX /etc/letsencrypt/live /etc/letsencrypt/archive'
# 注意：公网证书本来就不是机密，o+r 安全
```

---

## 6. SSH 凭据与访问控制

### 6.1 当前凭据（2026-09-10 更新）

| 用户 | 密钥 | 说明 |
|---|---|---|
| admin | ed25519（王健俊 Mac `~/.ssh/id_ed25519` 等） | 日常运维建议走这个 |
| root | 同一公钥也在 `/root/.ssh/authorized_keys` | **可直接 SSH**（2026-09-10 确认；此前文档误记为禁用）。root 下跑 admin 仓库的 git 需 `git config --global --add safe.directory /home/admin/labmemory.new` 或 `sudo -u admin git …` |

### 6.2 添加新成员

```bash
# 在新成员机器上生成密钥对
ssh-keygen -t ed25519 -C "新成员 <邮箱>"

# 新成员把公钥发给 admin
# admin 在服务器上：
ssh admin@<SERVER_IP>
echo "ssh-ed25519 AAAA...新成员公钥" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### 6.3 撤销某成员

```bash
ssh admin@<SERVER_IP>
# 备份 authorized_keys
cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak.$(date +%s)
# 编辑移除对应行
nano ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### 6.4 建议加 SSH alias

在 `~/.ssh/config` 加入：

```
Host labmem-prod
    HostName <SERVER_IP>
    User admin
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 3
    KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group-exchange-sha256
```

---

## 7. 监控告警（待建设）

当前**没有**自动告警。建议优先级：

| 级别 | 项 | 实现 |
|---|---|---|
| P1 | 平台进程消失 | systemd `OnFailure=` 触发邮件/钉钉 |
| P1 | 磁盘 >80% | cron 脚本 + 告警 |
| P2 | 证书 <7 天过期 | certbot 自带 + 邮件 hook |
| P2 | 备份缺失/损坏 | 备份脚本末尾加 alert |
| P3 | API 响应时间 P95 > 2s | nginx access log + 分析 |

短期方案：crontab 加巡检脚本，失败发邮件：

```bash
# /home/admin/labmemory/scripts/health_check.sh
#!/bin/bash
curl -fsS http://127.0.0.1:8081/health || echo "ALERT: platform down" | mail -s "LabMemory DOWN" admin@example.com
df -h / | awk 'NR==2 {if ($5+0 > 80) print "ALERT: disk " $5 | "mail -s \"LabMemory DISK\" admin@example.com"}'
```

---

## 8. 关联文档

- [`../infrastructure/servers.md`](../infrastructure/servers.md) — 服务器现状、问题清单
- [`../infrastructure/deployment.md`](../infrastructure/deployment.md) — 部署 checklist
- [`../../INTEGRATION.md`](../../INTEGRATION.md) — 启动命令、配置项