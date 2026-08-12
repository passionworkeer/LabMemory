# 部署指南

## 目录

- [系统要求](#系统要求)
- [环境准备](#环境准备)
- [飞书应用配置](#飞书应用配置)
- [平台对接配置](#平台对接配置)
- [部署步骤](#部署步骤)
- [运行方式](#运行方式)
- [监控与日志](#监控与日志)
- [常见问题](#常见问题)

---

## 系统要求

### 硬件要求

| 配置 | 最低要求 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核 |
| 内存 | 2 GB | 4 GB |
| 磁盘 | 10 GB | 20 GB |
| 网络 | 可访问飞书开放平台 | 稳定公网连接 |

### 软件要求

- Python 3.10+（见 `requirements.txt`）
- **飞书 CLI（`lark-cli`）**：Real 模式的硬依赖。妙记读取、任务创建、卡片下发、多维表格、云文档全部通过 `subprocess` 调用 `lark-cli`，未安装会直接抛「lark-cli 未安装，请先安装飞书 CLI」。仅 Aily 走 HTTP。Mock 模式不需要。
- 操作系统：Linux / macOS / Windows
- （可选）systemd / supervisor 用于进程管理

---

## 环境准备

### 1. 下载代码

```bash
# 克隆或复制项目到服务器
cd /opt
git clone <repository-url> feishu-orchestrator
cd feishu-orchestrator
```

### 2. 检查 Python 版本

```bash
python3 --version
# 确保 Python >= 3.10
```

### 3. 创建虚拟环境（推荐）

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows
```

### 4. 安装依赖

```bash
# 运行时依赖见 requirements.txt（当前唯一外部依赖为 python-dotenv）
pip install -r requirements.txt
```

### 5. 安装并授权飞书 CLI（Real 模式必做）

```bash
# 安装后确认可执行
lark-cli --version

# 绑定 Hermes 工作区中的飞书应用凭据（复用 Hermes 的 FEISHU_APP_ID）
lark-cli config bind --source hermes --identity user-default

# 完成 user 身份授权（私有妙记读取必需）
lark-cli auth login --domain "minutes,task,im,base,docs" --as user
```

Mock 模式可跳过本步。如果跳过后又切到 `RUN_MODE=real`，链路会在第一次调用妙记 / 卡片 / 任务时抛「lark-cli 未安装，请先安装飞书 CLI」。

---

## 飞书应用配置

### 1. 创建飞书企业自建应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 进入「开发者后台」→「创建企业自建应用」
3. 填写应用名称、描述等信息
4. 记录 App ID 和 App Secret

### 2. 配置权限

在「权限管理」中添加以下权限：

| 权限名称 | 权限标识 | 身份 | 用途 |
|---------|---------|------|------|
| 读取妙记 | `minutes:minute:read` | User | 读取用户私有妙记 |
| 读取会议信息 | `vc:meeting:read` | App | 获取会议元信息 |
| 发送消息 | `im:message:send_as_bot` | App | 发送交互卡片 |
| 管理任务 | `task:task:write` | App | 创建和更新飞书任务 |
| 管理多维表格 | `bitable:app:write` | App | 写入协作台账 |
| 管理云文档 | `docx:document:write` | App | 发布知识文档 |

### 3. 配置事件订阅

在「事件订阅」中配置：

**请求地址**：
```
https://your-domain.com/webhook/event
```

**订阅事件**：
- `meeting.ended_v1` - 会议结束
- `minutes.minute.generated_v1` - 妙记生成

**加密策略**：
- 记录 Encrypt Key 和 Verification Token
- **Encrypt Key 是 Real 模式验签的必填项**：填入 `CARD_CALLBACK_ENCRYPT_KEY`。留空时 `/webhook/event` 与 `/webhook/card` 会一律返回 401（空密钥会使签名退化为可伪造的固定哈希，因此不放行），启动日志会显式告警

### 4. 配置卡片回调

在「应用功能」→「机器人」→「交互卡片」中配置：

**请求地址**：
```
https://your-domain.com/webhook/card
```

### 5. 发布版本

1. 在「版本管理与发布」中创建新版本
2. 提交审核
3. 企业管理员审批通过后生效

---

## 平台对接配置

### 1. 获取平台 API 凭证

联系 LabMemory 平台管理员获取：
- API Base URL
- API Key
- 接口文档

### 2. 配置平台回调地址

在平台后台配置飞书侧回调地址：
```
https://your-domain.com/webhook/platform
```

---

## 部署步骤

### 1. 配置环境变量

```bash
# 复制环境变量模板到 config/.env
cp config/env.example config/.env

# 编辑
vi config/.env
```

> **路径必须是 `config/.env`**。`core/config.py` 只加载 `config/.env`；放到项目根的 `.env` 不会报错，但所有配置读不到、`RUN_MODE` 静默退回 `mock`，看起来接上了实际仍在跑模拟数据。

### 2. 关键配置项说明

```bash
# ============================================
# 运行模式
# ============================================
RUN_MODE=real  # mock / real

# ============================================
# 飞书应用配置
# ============================================
FEISHU_APP_ID=cli_xxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxx

# 租户 Access Token（短期，建议用 App ID/Secret 自动获取）
FEISHU_TENANT_ACCESS_TOKEN=t-xxxxxxxxxx

# 用户 Access Token（读取妙记需要，需用户 OAuth 授权）
FEISHU_USER_ACCESS_TOKEN=u-xxxxxxxxxx

# ============================================
# Aily 配置
# ============================================
AILY_API_BASE=https://aily.feishu.cn/api
AILY_SKILL_ID=skill_xxxxxxxxxx
AILY_API_KEY=xxxxxxxxxx

# ============================================
# LabMemory 平台配置
# ============================================
PLATFORM_API_BASE=https://labmemory.example.com/api
PLATFORM_API_KEY=xxxxxxxxxx

# ============================================
# 多维表格配置
# ============================================
BASE_APP_TOKEN=bascnxxxxxxxxxx
BASE_TABLE_ID=tblxxxxxxxxxx

# ============================================
# 服务配置
# ============================================
SERVER_HOST=0.0.0.0
SERVER_PORT=8080

# ============================================
# 重试配置
# ============================================
MAX_RETRIES=5
RETRY_BASE_DELAY=1
```

### 3. 初始化数据目录

```bash
# 目录会自动创建，也可以手动创建
mkdir -p data/state
mkdir -p data/idempotency
mkdir -p data/integration_logs
mkdir -p logs
```

### 4. 健康检查

```bash
python scripts/health_check.py
```

确保所有检查项都通过。

---

## 运行方式

### 方式一：直接运行（开发/测试）

```bash
# 启动 Webhook 服务
python -m core.webhook_server
```

### 方式二：后台运行（简单部署）

```bash
# 后台运行
nohup python -m core.webhook_server > logs/server.log 2>&1 &

# 查看日志
tail -f logs/server.log

# 停止服务
pkill -f "core.webhook_server"
```

### 方式三：systemd 管理（生产推荐）

创建 `/etc/systemd/system/feishu-orchestrator.service`：

```ini
[Unit]
Description=LabMemory Feishu Orchestrator
After=network.target

[Service]
Type=simple
User=deploy
WorkingDirectory=/opt/feishu-orchestrator
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/feishu-orchestrator/venv/bin/python -m core.webhook_server
Restart=always
RestartSec=5

# 日志
StandardOutput=append:/opt/feishu-orchestrator/logs/server.log
StandardError=append:/opt/feishu-orchestrator/logs/server.log

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
# 重载配置
systemctl daemon-reload

# 启动服务
systemctl start feishu-orchestrator

# 设置开机自启
systemctl enable feishu-orchestrator

# 查看状态
systemctl status feishu-orchestrator

# 查看日志
journalctl -u feishu-orchestrator -f
```

### 方式四：Docker 部署

创建 `Dockerfile`：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN mkdir -p data logs

EXPOSE 8080

CMD ["python", "-m", "core.webhook_server"]
```

构建和运行：

```bash
# 构建镜像
docker build -t feishu-orchestrator .

# 运行容器
docker run -d \
  --name feishu-orchestrator \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  --env-file config/.env \
  --restart always \
  feishu-orchestrator

# 查看日志
docker logs -f feishu-orchestrator
```

---

## 监控与日志

### 1. 健康检查端点

```bash
# 检查服务是否正常
curl http://localhost:8080/health

# 预期返回
# {"status": "ok"}
```

### 2. 日志位置

| 日志类型 | 路径 | 说明 |
|---------|------|------|
| 服务日志 | `logs/server.log` | Webhook 服务运行日志 |
| 集成日志 | `data/integration_logs/integration_YYYYMMDD.jsonl` | 所有外部调用日志 |
| 状态数据 | `data/state/` | 状态机状态 |
| 幂等记录 | `data/idempotency/` | 幂等控制记录 |

### 3. 集成日志查看

```bash
# 查看今天的日志
cat data/integration_logs/integration_$(date +%Y%m%d).jsonl | python -m json.tool

# 查看失败的调用
grep '"status": "failed"' data/integration_logs/integration_$(date +%Y%m%d).jsonl

# 统计调用次数
wc -l data/integration_logs/integration_$(date +%Y%m%d).jsonl
```

### 4. 管理 CLI

```bash
# 启动管理控制台
python scripts/admin_cli.py
```

功能：
- 查看流程列表和详情
- 重放指定流程
- 手动触发流程（妙记链接 / 文本输入）
- 查看集成日志
- 查看状态机状态
- 查看多维表格台账
- 查看知识文档
- 重置演示环境

---

## 常见问题

### Q1: 服务启动了但收不到事件？

**排查步骤**：
1. 检查飞书事件订阅配置的 URL 是否正确
2. 检查服务器防火墙/安全组是否开放了 8080 端口
3. 检查 URL 验证是否通过（首次配置需要响应 challenge）
4. 查看服务日志是否有请求到达
5. 若日志里全是 401，见 Q9（验签）

### Q2: 妙记读取失败，提示权限不足？

**原因**：BOT 身份无法读取用户私有妙记。

**解决方案**：
1. 使用用户 OAuth 授权获取 User Access Token
2. 或者将妙记设置为企业公开
3. 演示场景可以用 Mock 模式

### Q3: Aily 调用超时怎么办？

**原因**：会议内容太长，输入 token 太多。

**解决方案**：
1. 系统已内置分段处理（按章节分段）
2. 调整 `aily_adapter.py` 中的 `max_segment_chars` 参数
3. 增加超时时间和重试次数

### Q4: 如何切换 Mock / Real 模式？

```bash
# 修改 config/.env 文件
RUN_MODE=mock  # 或 real

# 重启服务
systemctl restart feishu-orchestrator
```

切到 `real` 前先确认三件事：`lark-cli` 已安装并授权、`config/.env`（不是根目录 `.env`）已填凭据、`CARD_CALLBACK_ENCRYPT_KEY` 非空。

### Q5: 如何重置所有数据？

```bash
# 方式一：使用管理 CLI
python scripts/admin_cli.py
# 选择 10. 重置演示环境

# 方式二：手动删除
rm -rf data/state/*
rm -rf data/idempotency/*
rm -rf data/integration_logs/*
```

### Q6: 飞书限流了怎么办？

**现象**：返回错误码 9999999 或 rate limit 相关错误。

**解决方案**：
1. 系统已内置自动退避重试
2. 批量操作时增加间隔
3. 联系飞书技术支持提升配额

### Q7: 如何与平台侧联调？

```bash
# 启动 Mock Platform Server
python -m mock.mock_server 8081

# 修改 config/.env
PLATFORM_API_BASE=http://localhost:8081
PLATFORM_API_KEY=mock-key

# 重启服务
systemctl restart feishu-orchestrator
```

### Q8: 如何备份数据？

```bash
# 备份整个 data 目录
tar -czf backup-$(date +%Y%m%d).tar.gz data/

# 恢复
tar -xzf backup-20260805.tar.gz
```

### Q9: Real 模式下 webhook 全部返回 401？

**原因**：验签未通过。Real 模式对 `/webhook/event` 与 `/webhook/card` 强制验签，算法为 `sha256(timestamp + nonce + encrypt_key + raw_body)` 的小写十六进制摘要，取请求头 `X-Lark-Request-Timestamp` / `X-Lark-Request-Nonce` / `X-Lark-Signature`。

**排查顺序**：
1. `CARD_CALLBACK_ENCRYPT_KEY` 是否为空 —— 空值一律判失败
2. 该值是否与开发者后台「加密策略」里的 **Encrypt Key** 一致（不是 Verification Token）
3. 服务器时间是否偏移超过 300 秒 —— 超出时间窗会被判为重放
4. 是否有反向代理改写了请求体（验签基于原始字节，任何重新序列化都会导致摘要不匹配）

Mock 模式跳过验签，启动日志会打印「验签已跳过」。

### Q10: Real 模式如何确认失败可诊断、资源创建没有假成功？

Real 模式下所有 lark-cli 失败、授权错误、超时和响应格式错误都应在 `data/integration_logs/integration_YYYYMMDD.jsonl` 中留下 `failed` 记录；任务创建必须返回非空 `task_guid`，Base 写入必须返回 `record_id`，文档发布必须返回 `doc_token`。发现失败时先按 `request_id` 检索整条调用链，不要手动重复点击审批按钮。

上线前建议按以下顺序执行：

```bash
python scripts/health_check.py
lark-cli minutes +search --query "上线验收" --dry-run --as user
lark-cli task +create --summary "LabMemory 上线验收任务" --description "验收后可删除" --idempotency-key "labmemory-release-check" --dry-run --as bot
```

确认失败原因后，修正配置并重试同一业务键；不要删除集成日志和幂等记录来“恢复”真实链路。

### Q11: Real 模式报「lark-cli 未安装，请先安装飞书 CLI」？

**原因**：妙记、任务、卡片、多维表格、云文档均通过 `subprocess` 调用 `lark-cli`，它是 Real 模式的硬依赖。

**解决**：安装后执行 `lark-cli config bind --source hermes --identity user-default` 绑定应用，再执行 `lark-cli auth login --domain "minutes,task,im,base,docs" --as user` 完成用户授权。确认 `lark-cli --version` 可执行且与服务进程同一 PATH（systemd / Docker 环境下尤其注意 PATH、钥匙串与运行用户差异）。

### Q11: 配置填了却不生效，`RUN_MODE=real` 也没切过去？

**原因**：`.env` 放错位置。`core/config.py` 只加载 `config/.env`，放到项目根不会报错，只是全部读不到默认值。

**解决**：确认文件路径为 `config/.env`。用 `python scripts/health_check.py` 查看输出的运行模式是否为 Real。

---

## 性能优化建议

1. **使用 SSD 存储**：状态和日志文件读写频繁，SSD 性能更好
2. **定期清理旧数据**：配置定时任务清理 30 天前的日志和幂等记录
3. **监控内存使用**：Mock 模式下内存状态会持续增长，生产环境用 Real 模式
4. **配置反向代理**：使用 Nginx 做反向代理，支持 HTTPS 和负载均衡

---

## 安全建议

1. **不要把 `config/.env` 提交到代码仓库**（仓库根 `.gitignore` 已忽略 `.env` 与 `config/.env`）
2. **定期轮换 API Key 和 Secret**
3. **配置 HTTPS**：使用 Nginx + Let's Encrypt
4. **限制访问 IP**：飞书回调 IP 白名单
5. **日志脱敏**：系统已自动脱敏敏感字段，定期检查
6. **最小权限原则**：飞书应用只申请必要的权限

---

## 联系与支持

如有问题，请联系：
- 项目负责人：韩广宁
- 项目文档：README.md
- 接口契约：contracts/ 目录
