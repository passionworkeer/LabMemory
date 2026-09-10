# Aily × LabMemory MCP 接入指南

> 本文是 OpenSpec change `add-aily-mcp-server` 的产物；目的是把飞书 Aily 企业版
> 与 LabMemory 平台通过**标准 MCP 协议（SSE 传输）**打通，让 Aily 直接调用平台
> 暴露的 10 个可信决策工具。
>
> **Aily 侧只做两件事**：
> 1. 把新 skill [`LabMemory 决策记忆/labmemory-decision-memory/SKILL.md`](./LabMemory%20决策记忆/labmemory-decision-memory/SKILL.md)（v1.0.8）配成 Aily 技能；
> 2. 把 MCP Server 地址（含 `PLATFORM_API_KEY`）配到 Aily 的 MCP 接入页。
>
> 旧版 skill `docs/aily-skill/skill-prompt.md` **已被新版本替代**（顶部有 banner 标注），
> 仅作历史参考保留。
>
> **LabMemory 侧已完成**：SSE 暴露 10 个工具 + Bearer 鉴权 + Aily 出口 IP 白名单 + Webhook 推回（备用通道）。

## 1. 协议与传输

- **协议**：MCP（Model Context Protocol），标准 JSON-RPC over SSE。
- **传输**：HTTP + SSE（Server-Sent Events），无 streamable HTTP。
- **端点**：
  - GET `/mcp/sse` — Aily 客户端入口（建立 server→client SSE 流）
  - POST `/mcp/messages` — Aily 把 client→server 消息 POST 到此
  - GET `/mcp/manifest` — 工具清单（自检用）
- **握手**：Aily 发起 SSE 连接后，先做 `initialize` → `notifications/initialized` → `tools/list`，
  之后用 `tools/call` 触发具体工具。

## 2. 鉴权

**核心约束（决定鉴权方式）**：飞书 Aily 「添加自定义 MCP」**只支持 name + url + desc 三项**，
没有 Authorization Header 配置入口（一年多内部反馈未支持，详见飞书内部讨论）。
官方默许的兼容方式是把鉴权信息**拼进 URL queryParam**（参考高德 MCP
`https://mcp.amap.com/sse?key=YOUR_KEY`，与本服务同模式）。

**LabMemory MCP Server 同时支持两种鉴权**（取一即可）：

| 方式 | 何时用 |
|---|---|
| `https://<your-domain.com>/mcp/sse?token=<PLATFORM_API_KEY>` | **Aily 接入的主路径**（后台无法配 Header） |
| `https://<your-domain.com>/mcp/sse` + `Authorization: Bearer <PLATFORM_API_KEY>` | curl 自检 / 本地调试 / 未来若 Aily 支持 Header |

两种方式**优先级**：Authorization Bearer Header > URL `?token=` / `?key=` / `?api_key=`。
其中 queryParam 还兼容 `token` / `key` / `api_key` 三种命名（高德用 key、Aily 文档示例用 token）。

**MCP 协议设计**：鉴权**只在 SSE 握手（GET /sse）时校验一次**。后续 POST /messages 由
MCP SDK 自动分发的 UUID v4 session_id 路由（128 位熵），这是 MCP 协议本身的会话模型，
与高德 / 社区实现完全一致。**不要**担心 Aily 后续调用工具时会丢 token。

> **身份来源（MCP 是机器对机器，非用户身份）**：MCP Server 不接受 `x-aily-user` 之类的客户端
> 自报身份头（防伪造）。所有需要用户身份的字段（`reviewer`、`assignee`、`executor`）由
> **Aily 模型在工具参数里显式传入**，由平台侧 `_resolve_actor()` 按 username / feishu_user_id 解析，
> 解析失败时按既定规则降级（如默认回 PI）。审计追溯走平台 `actor_id` + webhook correlation_id。

### 2.2 备用方案：无鉴权模式（`MCP_REQUIRE_AUTH=false`）

若 Aily 后台 URL 校验拒绝带 `?token=` 的输入（报"请输入合法的 URL"），可临时切到
无鉴权模式：服务端跳过 Bearer 校验，Aily 后台填裸 URL，公网防护走 nginx IP rate limit。
本方案风险面有限（恶意调用被 schema + 状态机闸门拦下），详见 transport.py 注释与
`docs/aily-skill/skill-prompt.md` A6 备用方案。

## 3. 工具清单（10 个，完整 schema 见 [`tools-manifest.json`](./aily-skill/tools-manifest.json)）

| # | 工具 | 一句话作用 |
|---|---|---|
| 1 | `labmemory_submit_transcript` | 收妙记/逐字稿 |
| 2 | `labmemory_submit_extraction` | Aily 抽取结果回写 |
| 3 | `labmemory_create_review` | 建决策复核项 |
| 4 | `labmemory_submit_verdict` | 复核 verdict 通过/驳回 |
| 5 | `labmemory_issue_version` | 签发参数版本（幂等） |
| 6 | `labmemory_preflight_check` | 执行前自检（六道闸门） |
| 7 | `labmemory_submit_execution` | 实际执行结果回写 |
| 8 | `labmemory_update_passport` | 更新护照/主张/边界 |
| 9 | `labmemory_publish_knowledge` | 发布知识 |
| 10 | `labmemory_create_reverify` | 创建复验任务 |

## 4. Aily 侧配置（飞书后台）

1. 进入 Aily 企业版后台 → **技能** → **新建技能**；
2. 粘贴 [`skill-prompt.md`](./aily-skill/skill-prompt.md) 的 Part B 提示词正文到「提示词」框；
3. 切到 **MCP** 页 → **添加自定义 MCP**：
   - 名称：`labmemory`
   - 端点 URL：**`https://<your-domain.com>/mcp/sse?token=<PLATFORM_API_KEY>`**
     ⚠️ token 必须拼进 URL（**不要**在「鉴权」或「描述」里找 Bearer 字段——Aily 后台没有）
   - 描述：随便填
4. 保存并启用；Aily 会自动调 `tools/list` 拉取工具清单。

> **备用方案**：若 Aily 后台报"请输入合法的 URL"，参考 §2.2 切到无鉴权模式 + 裸 URL。
>
> **关于 CLI**：`aily-mcp install-remote --url ... --protocol sse` 同样没有 `--header` /
> `--auth` 参数，是 CLI 工具本身的限制。手动在 Aily 后台配 MCP 是当前唯一入口。

## 5. 部署 & 安全

### 5.1 Aily 出口 IP 白名单（必配）

飞书 Aily 通过固定出口 IP 访问平台（参见飞书官方文档），把以下段加入反向代理
或防火墙白名单：

```
# 飞书 Aily 出口 IP（来自飞书官方文档，需定期核对）
203.166.190.0/24
203.166.191.0/24
# ...
```

校验脚本：`scripts/check_aily_ip_allowlist.py`（详见源码）。

### 5.2 Nginx 示例

```nginx
# /etc/nginx/conf.d/labmemory-aily.conf
server {
    listen 443 ssl http2;
    server_name labmemory.example.com;

    # ... ssl config ...

    location /mcp/ {
        # 限制只允许 Aily 出口 IP
        allow 203.166.190.0/24;
        allow 203.166.191.0/24;
        deny all;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # SSE 必须
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;

        # 透传 Aily 用户头
        proxy_pass_header X-Aily-User;
    }
}
```

### 5.3 Cloudflare Workers / Tunnel

```yaml
# config.yml
tunnel: labmemory
ingress:
  - hostname: labmemory.example.com
    service: http://platform:8000
    originRequest:
      noTLSVerify: false
      connectTimeout: 30s
      # 在 worker 里加 IP 白名单
      # ...
  - service: http_status:404
```

### 5.4 平台侧环境变量

```bash
# .env（生产）
MCP_ENABLED=true
MCP_SSE_PATH=/mcp/sse
MCP_MESSAGES_PATH=/mcp/messages
PLATFORM_API_KEY=<长随机串 ≥32 字节>
```

> **C1 修复后**：`MCP_ALLOW_INSECURE_USER_HEADER` 已从 `.env.example` 与 `app/config.py` 删除。
> MCP Server 是**机器对机器**调用（Aily 后台 → 平台），不存在「信任客户端自报身份」场景；
> 详细理由见 `openspec/changes/archive/2026-08-15-add-aily-mcp-server/design.md` §3。

## 6. Webhook 触发链路

平台在以下事件触发 HMAC 签名 POST 回飞书（`webhook-payload.md` 详）：

| 事件 | 触发工具 | 推送内容 |
|---|---|---|
| `decision.pending` | `labmemory_create_review` | 飞书卡片给 PI/Lead |
| `preflight.blocked` | `labmemory_preflight_check` | 飞书任务卡片给执行人 |
| `execution.deviated` | `labmemory_submit_execution` | 偏差通知给 PI |
| `knowledge.ready` | `labmemory_publish_knowledge` | 飞书知识库 + 复验提醒 |
| `reverify.due` | `labmemory_create_reverify` | 飞书任务卡片给 assignee |

所有 webhook 都带 `X-LabMemory-Signature`（HMAC-SHA256）做防伪。

## 7. 限制 & 已知边界

- **返回值精简**：所有工具返回 ≤ 2 万字（去掉 transcript 全文等大字段）；
  完整数据通过 `jump_url` 在飞书卡片里给用户跳转。
- **DB Session 隔离**：每个工具调用独立 SessionLocal，事务内完成；
  **CancelledError 时显式 rollback + close**（M2 修复，避免 SQLite 单连接池被污染）。
- **DNS rebinding**：默认关闭（生产由反向代理保证 Host/Origin 校验）。
- **stateless 模式**：`Server.run(stateless=True)` —— 同一 Aily 实例可建立多个并发连接，
  协议层不绑定客户端会话。
- **仅 POST /messages**：GET /sse 是单向 server→client；客户端→服务端消息走 POST。

### 7.1 publish_knowledge 幂等（M4）

`labmemory_publish_knowledge` 是**幂等**操作：同一实验最新已发布结果再次调用时直接返回
原 `knowledge_id`，响应额外带 `"idempotent": true` 标志位。**不会**重复：

- 改写 `publisher_id` / `published_at` / `claim.knowledge_status`
- 触发 `knowledge.ready` webhook

Aily 在网络抖动重试 / 用户误重复点击时安全。幂等判定基于"该实验最新 Result 状态为
`published`"而非 `idempotency_key`，因为 Aily 调用无 ID。

### 7.2 /mcp/manifest 暴露范围（M5）

`GET /mcp/manifest` 经 Bearer 鉴权后**完整暴露** 10 个工具的 `name` / `description` /
`inputSchema`。**决策依据**：

- MCP 协议本身就是「带 Bearer 的契约」—— 没有不暴露工具的接入方案。
- Bearer 一旦泄漏，攻击者已知 MCP 集成关系，schema 暴露不构成新攻击面。
- 描述字段含内部模型名（`labmemory_*`）是有意为之，让 Aily 接入方在集成阶段清楚工具能力边界，
  避免黑盒调用。

**不在 manifest 暴露的**：平台内部状态机细节、数据库 schema、其它内部 endpoint 路径。
仅当用户持 Bearer 时才可见；生产环境可由反向代理把 `/mcp/manifest` 限制为内网访问。

### 7.3 身份模型（H4 / M6）

MCP Server **不接受**任何客户端自报身份头（如 `x-aily-user`、`x-user-email`）。来源：

- **威胁模型**：MCP 调用者是 Aily 服务账号，不是终端用户；任何客户端可控的「我是用户 X」
  头部都是被伪造的输入，不是鉴权信号。
- **审计追溯**：平台在以下层做来源归属，不依赖头部：
  - `Authorization: Bearer <PLATFORM_API_KEY>` → 标识**机器**（Aily 实例 / 飞书企业版）
  - 工具参数中的 `reviewer` / `assignee` / `executor` → 标识**用户**（Aily 模型在 prompt 里填）
  - Webhook `X-LabMemory-Correlation-Id` → 串联**调用链**
- **降级策略**：工具参数中的用户名解析失败时（`_resolve_actor`），按业务规则回退 PI，
  保证责任门 / 状态机不卡死；该回退写入 `AuditEvent` 留痕。

## 8. 开发与测试

```bash
# 启服务
cd labmemory-platform
APP_ENV=development uvicorn app.main:app --reload --port 8000

# 看清单（无需起服务也行）
PYTHONIOENCODING=utf-8 APP_ENV=test python -m app.mcp_server.manifest

# Smoke test（Aily 模拟端）
scripts/smoke_aily_mcp.sh

# 跑全套 pytest
pytest tests/ -v
```

## 9. 排错速查

| 现象 | 排查 |
|---|---|
| Aily 后台报"请输入合法的 URL" | URL 里带了 `?token=...`；改成裸 URL `https://<your-domain.com>/mcp/sse` |
| Aily 保存后 tools/list 返空 | 域名或路径拼错；先 `curl https://<your-domain.com>/mcp/manifest` 验证（无鉴权模式下应直接 200 + 10 工具） |
| POST /mcp/messages 400 | 缺 session_id（SDK 校验）；从 SSE 流上 `event: endpoint` 事件拿 |
| SSE 连接建立后立刻断开 | nginx `proxy_buffering off` 漏配；连不上 SSE 心跳 |
| 工具返 isError=true code=not_found | ID 错；检查参数 ID 是否来自上一次工具调用的返回值 |
| 公网被恶意占用 SSE 连接 | 调高 nginx `limit_req` burst；或加 IP 白名单（详见 `deploy/README.md`） |

---

## 附录

- 完整 Skill 提示词：[`docs/aily-skill/skill-prompt.md`](./aily-skill/skill-prompt.md)
- 工具清单 JSON：[`docs/aily-skill/tools-manifest.json`](./aily-skill/tools-manifest.json)
- Webhook 推送规范：[`docs/aily-skill/webhook-payload.md`](./aily-skill/webhook-payload.md)
- 平台契约总览：[`AILY_INTEGRATION.md`](./AILY_INTEGRATION.md)
- OpenSpec change：`openspec/changes/add-aily-mcp-server/`