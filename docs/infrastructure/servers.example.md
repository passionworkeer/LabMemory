# 生产服务器规划与配置参考样例 (Server Architecture Reference)

> 本文件提供 LabMemory 生产服务器规划、系统配置、Nginx 反向代理与 Systemd 托管的**参考模板**。
> 生产部署可参考此拓扑与配置规范。
> 配套文档：[`deployment.md`](deployment.md)（部署 checklist）、[`../operations/runbook.md`](../operations/runbook.md)（运维 runbook）。

---

## 1. 推荐硬件规格

| 项 | 推荐配置（单节点标准型） | 生产高可用 / 评测集群 |
|---|---|---|
| CPU | 2 vCPU 以上（x86_64 或 ARM64） | 4~8 vCPU |
| 内存 | 2 GiB 物理内存 + 4 GiB Swap | 8 GiB 物理内存以上 |
| 系统盘 | 40 GiB SSD 以上 | 100 GiB SSD |
| 操作系统 | Ubuntu 22.04 / 24.04 LTS | Ubuntu 24.04 LTS / Debian 12 |
| Python | 3.12+ | 3.12+ |
| Node.js | 20+ LTS | 22+ LTS |
| 公网带宽 | 5 Mbps 峰值以上 | 按并发量评估 |

---

## 2. 系统用户与目录权限建议

建议使用非 root 专用运维用户（如 `admin`）运行平台服务，避免高权限安全风险：

```bash
# 建立专用运行用户
sudo useradd -m -s /bin/bash admin
sudo usermod -aG sudo admin

# 项目根目录
/home/admin/labmemory/
├── labmemory-platform/          # FastAPI 平台核心
│   ├── .env                    # 生产环境密钥（chmod 600）
│   ├── data/                   # SQLite 数据库与向量索引存储
│   └── frontend/               # 前端项目
├── backups/                    # SQLite 每日热备归档目录
└── .venv/                      # Python 虚拟环境
```

---

## 3. 核心服务架构与端口规划

| 端口 | 服务 | 绑定地址 | 访问范围 |
|---|---|---|---|
| `80` | Nginx (HTTP) | `0.0.0.0:80` | 公网（强制 301 重定向到 HTTPS） |
| `443` | Nginx (HTTPS) | `0.0.0.0:443` | 公网（对外提供 Web 前端与 MCP SSE） |
| `8081` | FastAPI (labmemory-platform) | `127.0.0.1:8081` | 仅本地监听，由 Nginx 反向代理 |
| `8080` | feishu-orchestrator (可选) | `127.0.0.1:8080` | 仅本地监听（备用事件编排通道） |

---

## 4. Systemd 托管参考 (`labmemory-platform.service`)

在 `/etc/systemd/system/labmemory-platform.service` 配置服务单元：

```ini
[Unit]
Description=LabMemory Platform (FastAPI uvicorn :8081)
After=network.target

[Service]
Type=simple
User=admin
Group=admin
WorkingDirectory=/home/admin/labmemory/labmemory-platform
ExecStart=/home/admin/labmemory/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8081
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

启停命令：
```bash
sudo systemctl daemon-reload
sudo systemctl enable labmemory-platform
sudo systemctl start labmemory-platform
sudo systemctl status labmemory-platform
```

---

## 5. Nginx 反向代理与 MCP SSE 配置

在 `/etc/nginx/sites-available/labmemory` 配置反代与 SSE 流式长连接保障：

```nginx
server {
    listen 80;
    server_name <your-domain.com>;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name <your-domain.com>;

    ssl_certificate /etc/letsencrypt/live/<your-domain.com>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<your-domain.com>/privkey.pem;

    # 1. 前端与常规 API 路由
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 2. Aily MCP SSE 长连接路由（关键：禁用缓存并调整超时）
    location /mcp/sse {
        proxy_pass http://127.0.0.1:8081/mcp/sse;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        chunked_transfer_encoding on;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 6. 定期体检与维护 SOP

| 检查项 | 检查命令 | 正常判断标准 |
|---|---|---|
| 服务健康 | `curl -fsS http://127.0.0.1:8081/health` | 返回 `{"status":"ok"}` |
| MCP 清单 | `curl -fsS http://127.0.0.1:8081/mcp/manifest` | 返回 10 个工具定义 |
| 备份完整性 | `ls -lt /home/admin/labmemory/backups/` | 存在每日最新快照，文件大小 > 0 |
| 进程状态 | `sudo systemctl status labmemory-platform` | `active (running)` |
| 磁盘与内存 | `df -h / && free -m` | 磁盘利用率 < 85%，可用内存 > 300MB |
| SSL 证书有效期 | `certbot certificates` | 剩余有效期 > 30 天 |
