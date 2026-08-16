## 1. 依赖与配置

- [ ] 1.1 `labmemory-platform/requirements.txt`：新增 `mcp[cli]>=1.0,<2.0`、`sse-starlette>=2.0`。
- [ ] 1.2 `labmemory-platform/.env.example`：新增 `MCP_ENABLED=true`、`MCP_SSE_PATH=/mcp/sse`、`MCP_MESSAGES_PATH=/mcp/messages`、`MCP_ALLOW_INSECURE_USER_HEADER=false`（默认 false，仅在 IP 白名单通过时才信任 `x-aily-user`）。
- [ ] 1.3 `app/config.py::Settings`：新增 `MCP_ENABLED: bool = True`、`MCP_SSE_PATH: str = "/mcp/sse"`、`MCP_MESSAGES_PATH: str = "/mcp/messages"`、`MCP_ALLOW_INSECURE_USER_HEADER: bool = False`（仅 dev 沙箱打开，生产必须依赖反向代理 IP 白名单）。

## 2. 共享 helpers 抽取（重构 `aily.py`）

- [ ] 2.1 新建 `labmemory-platform/app/services/aily_helpers.py`：从 `app/api/aily.py` 抽出以下纯函数模块：
  - `_experiment(db, exp_id) -> Experiment`
  - `_resolve_actor(db, feishu_user_id_or_username) -> User | None`
  - `_ref_put(db, ref_type, aily_id, platform_type, platform_id, payload=None)`
  - `_ref_get(db, ref_type, aily_id) -> IntegrationRef | None`
  - `_meeting_from_ref(db, ref_type, aily_id) -> Meeting | None`
  - `_build_candidates(db, exp, payload) -> list[dict]`
  - `_confirm_decision(db, meeting, review, actor, comment) -> (claim, task, publish_status, gate, conflicts)`
- [ ] 2.2 `app/api/aily.py`：删除原私有 helpers，改 `from app.services.aily_helpers import ...`；**所有 10 个 HTTP endpoint 行为零变化**。
- [ ] 2.3 跑 `pytest tests/test_hardening_smoke.py tests/test_aily_integration.py` 全量通过（HTTP 接口行为回归）。

## 3. MCP Server 模块

- [ ] 3.1 `labmemory-platform/app/mcp_server/__init__.py`：
  ``` from mcp.server import Server
  mcp_server = Server(name="labmemory", version="1.0.0") ```
- [ ] 3.2 `labmemory-platform/app/mcp_server/tools.py`：注册 10 个 `@mcp_server.list_tool()` / `@mcp_server.call_tool()`，每个工具：
  - name 前缀 `labmemory_`
  - 入参：直接对接 `app/services/aily_helpers.py` + 已有 `app/api/aily.py` 的 endpoint 内部实现
  - 出参：精简版（≤2 万字），含 `jump_url`
- [ ] 3.3 `labmemory-platform/app/mcp_server/auth.py`：
  - `verify_mcp_bearer(request) -> bool`：复用 `verify_platform_api_key`
  - `extract_aily_user(request) -> str | None`：从 `x-aily-user` 头读取；非白名单 IP 时返回 None
- [ ] 3.4 `labmemory-platform/app/mcp_server/transport.py`：
  - 基于 `sse-starlette` 把 `mcp_server` 包装成 Starlette app
  - 在 SSE 端点挂载：`add_route(MCP_SSE_PATH, handle_sse)`、`add_route(MCP_MESSAGES_PATH, handle_messages)`
  - 心跳：每 15 秒发 `event: ping`
- [ ] 3.5 `labmemory-platform/app/mcp_server/manifest.py`：
  - `MANIFEST: dict = {"server": {...}, "auth": {...}, "tools": [...]}` —— 10 个工具的完整 JSON Schema
  - 提供 `python -c "from app.mcp_server.manifest import MANIFEST; print(MANIFEST)"` 自检

## 4. FastAPI 集成

- [ ] 4.1 `app/main.py`：在现有 router mount 之后追加：
  ``` if settings.MCP_ENABLED:
      from app.mcp_server.transport import mount_mcp
      mount_mcp(app) ```
- [ ] 4.2 启动时 import 自检：`python -c "from app.main import app; print([r.path for r in app.routes])"` 输出应含 `/mcp/sse`、`/mcp/messages`、`/v1/transcripts` 等。
- [ ] 4.3 不改现有路由签名、不改现有中间件顺序。

## 5. 文档交付物（`docs/aily-skill/`）

- [ ] 5.1 `docs/aily-skill/skill-prompt.md`：单 Skill《LabMemory 决策记忆》系统提示词。结构：
  - 角色定位（你是 LabMemory 决策记忆助手）
  - 12 步链路总览图（文字版）
  - 10 个 MCP 工具调用顺序与典型参数
  - 失败降级路径（闸门未过 / 范围缺失 / 证据失效）
  - 诚实边界（不编造实验编号 / 不擅自批准 / 不修改历史版本）
- [ ] 5.2 `docs/aily-skill/tools-manifest.json`：从 `app/mcp_server/manifest.py` 同步导出，与 `MANIFEST` 内容一致。
- [ ] 5.3 `docs/aily-skill/webhook-payload.md`：5 类出站 webhook payload schema（decision.pending / preflight.blocked / execution.deviated / knowledge.ready / reverify.due）+ HMAC 验签方式 + 当前推 Aily / 未来可切飞书侧编排器的说明。
- [ ] 5.4 仓库根 `AILY_MCP.md`：Aily 侧接入步骤：
  1. 部署平台并获取 MCP SSE URL（`https://{base}/mcp/sse`）
  2. 在 Aily 工作助手「连接服务」粘贴 URL + Bearer Token
  3. 把 `skill-prompt.md` 粘贴为智能体系统提示词
  4. 跑通最小场景测试（会议 → 抽取 → 复核 → 版本）

## 6. 部署与安全

- [ ] 6.1 `labmemory-platform/scripts/check_aily_ip_allowlist.py`：从 Aily 文档固化白名单（`101.126.59.88-92` + `122.14.241.34-38`），检查当前 Nginx/Cloudflare 配置是否含这些 IP（提示用户检查 `nginx.conf` / Cloudflare WAF 规则），无法自动校验时给出 manual checklist。
- [ ] 6.2 Nginx 配置示例（写入 `AILY_MCP.md` 附录）：
  ```
  location /mcp/sse {
      proxy_buffering off;
      proxy_cache off;
      proxy_set_header X-Accel-Buffering no;
      allow 101.126.59.88/32; ... ;
      deny all;
  }
  ```
- [ ] 6.3 Cloudflare Transform Rule 示例（写入 `AILY_MCP.md` 附录）。

## 7. 测试

- [ ] 7.1 `labmemory-platform/tests/test_mcp_server.py`：
  - 每个工具的入参/出参 schema 校验
  - Bearer 失败返回 403
  - `x-aily-user` 命中 / 未命中 / 伪造 三种情况
  - 返回值 `jump_url` 字段存在性
- [ ] 7.2 `labmemory-platform/scripts/smoke_aily_mcp.sh`：用 `curl -N` 模拟 SSE 连接，依次调 10 个工具，验证端到端。
- [ ] 7.3 `pytest tests/` 全量通过（HTTP `/v1/*` 接口行为零回归）。
- [ ] 7.4 `python -c "from app.main import app"` 通过（import 自检）。
- [ ] 7.5 `python -c "from app.mcp_server.manifest import MANIFEST; print(MANIFEST['server'])"` 通过。
- [ ] 7.6 前端 `npx tsc --noEmit` 与 `npm run build` 通过（无前端改动，验证现有前端无回归）。
- [ ] 7.7 `openspec validate add-aily-mcp-server` 通过。

## 8. 归档

- [ ] 8.1 `openspec archive add-aily-mcp-server --yes`（实施完成 + 7.x 验证通过后执行）。