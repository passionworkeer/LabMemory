# Proposal: 接入 Aily MCP Server（10 个 MCP 工具 + SSE）

## Why

Aily 企业版已支持标准 MCP 协议（见官方文档「添加自定义 MCP 工具」），传输方式 SSE / HTTPStreaming，工作助手「连接服务」可注册我们的 MCP Server URL。当前平台只有 HTTP `/v1/*` 入站接口（最近合并的 `add-aily-contract`），**Aily 侧必须自行包装成 Function Call 才能调用**，门槛高、配置散落、不利于企业级统一管理。

把 10 个 HTTP 接口**封装成标准 MCP 工具并以 SSE 长连接暴露**，Aily 后台一键注册即可获得全部 10 个 Function Call；同时配套一份《LabMemory 决策记忆》Skill 提示词，固化 Aily 的角色与调用顺序。

## What Changes

### 后端 — MCP Server（labmemory-platform/app/mcp_server/）

- **新增** `app/mcp_server/__init__.py`：`mcp.Server(name="labmemory", version="1.0.0")` 实例化。
- **新增** `app/mcp_server/tools.py`：10 个 `@mcp.tool()` 注册，对应现有 `app/api/aily.py` 的 10 个 HTTP 接口；工具签名只声明**输入字段 + 输出 schema**，业务逻辑**复用** `_experiment` / `_resolve_actor` / `_confirm_decision` / `_build_claim` / `_run_checks` 等已有 helpers，**不改领域逻辑**。
- **新增** `app/mcp_server/auth.py`：从请求头读取 `Authorization: Bearer {PLATFORM_API_KEY}` 验签（复用 `verify_platform_api_key`）+ 读取 `x-aily-user` 解析为平台 `User`（已有 `_resolve_actor` 支持 `feishu_user_id`）。
- **新增** `app/mcp_server/transport.py`：基于 `sse-starlette` 把 MCP SSE endpoint（默认 `/mcp/sse`）mount 到现有 FastAPI app，复用 CORS / 中间件链。
- **新增** `app/mcp_server/manifest.py`：导出每个工具的 JSON Schema（name / description / inputSchema），供 Aily 后台"自定义工具"手填或导入。
- **修改** `app/main.py`：在 mount 现有 `/v1/*` 之后挂载 `/mcp/sse`；保证两条入口**并存**（HTTP 直连 + MCP SSE）。
- **修改** `app/config.py`：新增 `MCP_ENABLED`（默认 `true`，MCP Server 与 `/v1/*` 共存；可独立关停）；`MCP_SSE_PATH`（默认 `/mcp/sse`）。
- **修改** `app/api/aily.py`：将每个 endpoint 的 `_experiment` / `_resolve_actor` / `_confirm_decision` 抽成可被 MCP tools 直接 import 复用的纯函数（MCP 工具与 HTTP 接口共享同一业务内核）。**不改 HTTP 路由行为**。
- **修改** `.env.example`：补 `MCP_ENABLED` / `MCP_SSE_PATH`。
- **修改** `labmemory-platform/requirements.txt`：新增 `mcp[cli]>=1.0` + `sse-starlette>=2.0`。

### 文档（仓库根 `docs/aily-skill/`）

- **新增** `docs/aily-skill/skill-prompt.md`：单 Skill《LabMemory 决策记忆》系统提示词，覆盖 12 步链路、工具调用顺序、参数模板、失败降级路径。
- **新增** `docs/aily-skill/tools-manifest.json`：10 个 MCP 工具的 manifest（name / description / inputSchema），可一键导入 Aily 后台"自定义工具"。
- **新增** `docs/aily-skill/webhook-payload.md`：5 类出站 webhook payload schema + 验签方式 + 接入指引（说明当前推 Aily，未来可切飞书侧编排器，本 change **不改 webhook 目标**）。

### 部署与安全

- **新增** `labmemory-platform/scripts/check_aily_ip_allowlist.py`：校验当前出口 IP 是否在 Aily 文档给出的白名单（`101.126.59.88-92`、`122.14.241.34-38`），提醒运维在反向代理/云防火墙放开。
- **新增** `AILY_MCP.md`（草版）：Aily 侧接入步骤（生成 MCP SSE URL、注册到工作助手「连接服务」、粘贴 Skill 提示词）。

### 规格基线

- **ADDED** `openspec/specs/aily-mcp-server/spec.md`：MCP Server 契约（鉴权、传输、工具清单、安全约束）。
- **不修改** 现有 `aily-contract` 规格与 `/v1/*` HTTP 契约。MCP Server 是 `/v1/*` 之上的适配层，二者**并存**（HTTP 仍供飞书侧编排器与外部脚本调用；MCP 专供 Aily）。

## Capabilities

### New Capabilities
- `aily-mcp-server`：标准 MCP 协议暴露 10 个工具，SSE 传输，Bearer + `x-aily-user` 鉴权；与现有 `/v1/*` HTTP 契约并存。

## Impact

- 代码：`labmemory-platform/app/mcp_server/` 新增约 6 个文件（约 600-800 行）；`app/api/aily.py` 抽出共享 helpers（重构但行为不变）；`app/main.py` + `app/config.py` + `requirements.txt` 小幅改动。
- API：**HTTP `/v1/*` 契约完全不动**；新增 `/mcp/sse` 一个端点。
- 数据：**零数据库改动**（MCP 工具复用现有 `IntegrationRef` 映射与全部领域模型）。
- 依赖：新增 `mcp[cli]>=1.0` + `sse-starlette>=2.0` 两个 PyPI 包。
- 性能：每个 MCP 调用与对应 HTTP 调用等价（共享业务内核）；SSE 长连接本身不引入额外开销。
- 安全：MCP endpoint 必须保密（仅 Aily 已知 URL）；`x-aily-user` 头需在 Nginx/Cloudflare 层验签防止伪造；部署侧需把 8 个 Aily 出口 IP 加入白名单。
- 保密：MCP 工具返回值须遵守 Aily「2 万字以内」建议；现有 `submit_transcript` 会返回整段 transcript → MCP 版本返回 `{transcript_id, segment_count, duration_sec, jump_url}`，**全文走 jump_url 由前端按需拉取**。

## Out of Scope

- 不实现 HTTPStreaming（先用 SSE；如未来 Aily 强制 HTTPStreaming 再加）。
- 不改 webhook 出站目标（仍推 Aily；切换到飞书侧编排器另起 change）。
- 不写 Skill 提示词的 A/B 评测（先用单 Skill 跑通）。
- 不做 MCP Server 的水平扩展（单实例足够；如未来 SSE 连接数 > 1000 再考虑）。