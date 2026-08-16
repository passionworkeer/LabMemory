# Design: 接入 Aily MCP Server

## 目标与约束

- 在 `labmemory-platform` 同进程内 mount 一个标准 MCP Server，SSE transport，暴露 10 个工具，复用现有 `/v1/*` HTTP 契约背后的全部领域逻辑。
- HTTP `/v1/*` 与 MCP `/mcp/sse` **并存**：HTTP 供飞书侧编排器与外部脚本；MCP 专供 Aily 工作助手「连接服务」注册。
- 鉴权：Bearer Token（复用 `verify_platform_api_key`）+ Aily 用户身份头 `x-aily-user`（解析为平台 `User`）。
- 不改领域逻辑、不改数据库 schema、不改现有契约。

## 关键决策

### D1 同进程 Mount SSE（不复用 FastAPI 原生 ASGI）

**选择**：用 `sse-starlette` 暴露 SSE endpoint，独立路由 `/mcp/sse`，挂在现有 FastAPI app 下。

**原因**：
- 飞书侧编排器与 Aily 都要调平台，复用同一 FastAPI 进程可避免双份 DB 连接池 / 双份鉴权中间件 / 双份运维。
- `mcp` Python SDK 提供 `mcp.run(transport="sse")`，可直接挂到 Starlette app。
- 与 HTTP `/v1/*` 共存，不冲突（路径空间分开：HTTP 是 `/v1/*`，MCP 是 `/mcp/sse`）。

### D2 工具实现：复用 `app/api/aily.py` 的 helpers

**选择**：MCP 工具不重复写业务，只**调用** `aily.py` 已有的 `_experiment` / `_resolve_actor` / `_confirm_decision` / `_build_claim` / `_run_checks` / `_ref_put`。

**重构**：
- 把 `aily.py` 里的 `build_candidates` / `confirm_decision` / `_resolve_actor` / `_experiment` / `_ref_put` / `_ref_get` 抽到 `app/services/aily_helpers.py`（纯函数模块）。
- MCP tools 与 HTTP endpoints **都 import** 这个 helpers 模块，行为零差异。
- HTTP endpoints 保持原签名（仅内部 import 路径微调）。

**原因**：避免逻辑漂移；MCP 与 HTTP 任一入口出问题，另一入口立即回归发现。

### D3 鉴权：Bearer + `x-aily-user` 双因子

**Bearer**：复用 `verify_platform_api_key`（接受 `Authorization: Bearer {key}` 或 `X-Platform-Api-Key`），不变。

**`x-aily-user`**：Aily 在每次调用 MCP 工具时携带（Feishu `user_id`，`ou_xxx` 格式），平台用 `_resolve_actor(db, header_value)`：
- 先查 `User.feishu_user_id == header_value`
- 找不到 → 回退 PI（与现有 HTTP 接口一致，避免 LLM 误传时阻断）

**鉴权顺序**：
1. SSE 连接建立：校验 Bearer → 通过则升级 SSE；不通过返回 403。
2. 每个 MCP tool call：再次校验 Bearer（防止长连接被劫持）+ 读 `x-aily-user` 上下文（注入到工具内部）。

### D4 返回值大小：遵守 Aily「2 万字以内」约束

| MCP 工具 | 现有 HTTP 返回 | MCP 返回（精简） |
|---|---|---|
| `submit_transcript` | 包含 segments 全文 | `{transcript_id, meeting_id, segment_count, duration_sec, jump_url}` |
| `submit_extraction` | 包含 `candidate_ids` | `{extraction_id, created, candidate_ids, jump_url}` |
| `create_review` | `{decision_id, jump_url}` | 同 |
| `submit_verdict` | 含 gate_report 全文 | `{ack, decision_id, version_id, task_id, publish_status, gate_report_summary, jump_url}` |
| `issue_version` | 含 params 全文 | `{version_id, created, publish_status, jump_url}` |
| `preflight_check` | 含 reasons 全文 | `{verdict, reasons[], boundary_check_summary, task_id, jump_url}` |
| `submit_execution` | `{execution_id, status}` | 同 |
| `update_passport` | `{passport_id, updated}` | 同 |
| `publish_knowledge` | `{knowledge_id, status}` | 同 |
| `create_reverify` | `{reverify_id, task_id}` | 同 |

**全文获取**：返回的 `jump_url` 指向平台前端详情页，Aily 在工具调用结果里**附链接**，告诉用户「详情看这里」。如 Aily 模型本身需要全文，提示词里告诉它「用 `/v1/*` HTTP 接口或前端页面拿详情」，**MCP 工具保持精简**。

### D5 工具 manifest：导出给 Aily 后台

`app/mcp_server/manifest.py` 输出 JSON：
```json
{
  "server": {"name": "labmemory", "version": "1.0.0", "transport": "sse", "url": "/mcp/sse"},
  "auth": {"bearer": "${PLATFORM_API_KEY}", "user_header": "x-aily-user"},
  "tools": [
    {"name": "submit_transcript", "description": "...", "inputSchema": {...}, "annotations": {...}},
    ...
  ]
}
```

Aily 后台「连接服务」→「添加自定义 MCP 工具」只需填：URL（`{base}/mcp/sse`） + Bearer Token；10 个工具自动发现。

### D6 部署安全

**Aily 出口 IP 白名单**（平台反向代理/云防火墙需放开）：
- `101.126.59.88` / `89` / `90` / `91` / `92`
- `122.14.241.34` / `35` / `36` / `37` / `38`

**MCP endpoint 保密**：
- 平台部署到公网时 `/mcp/sse` URL 用随机 path（如 `/mcp/sse/<random_token>`）防止扫到。
- 不在仓库文档/前端/任何用户可见路径暴露此 URL。
- SSE 长连接不持久化用户数据，仅作为调用通道。

**`x-aily-user` 防伪造**：
- 在 Nginx/Cloudflare 层校验请求来源 IP 在白名单内 → 才信任 `x-aily-user`；否则忽略该头并强制使用 PI 兜底。
- 记入审计日志（`AuditEvent`），便于追溯。

### D7 Skill 提示词骨架

《LabMemory 决策记忆》Skill 内容大纲：
1. **角色**：你是 LabMemory 决策记忆助手，负责把会议纪要编译为可信、可追溯的实验决策。
2. **场景识别**：飞书会议刚结束 → 走「会议→抽取→复核→版本→任务→执行→结果→知识」12 步链路。
3. **工具清单**：列出 10 个 MCP 工具及典型调用顺序。
4. **参数模板**：每个工具的关键参数示例（实验编号、参数版本号、用户身份等）。
5. **失败降级**：闸门未过 / 范围缺失 / 证据失效 → 返回阻断卡片，不要乐观放行。
6. **诚实边界**：不编造实验编号、不擅自批准、不修改历史版本；超出能力时引导用户走人工复核。

## 非目标

- 不实现 HTTPStreaming（先用 SSE）。
- 不改 webhook 出站目标。
- 不做 Skill 提示词的 A/B 评测或自动化回归。
- 不引入 MCP Server 集群（单实例 + SSE 长连接足够）。

## 风险

- **mcp SDK 稳定性**：`mcp` Python SDK 1.0+ 已稳定但生态较新；锁版本 `mcp>=1.0,<2.0`，CI 用真实 import 自检。
- **SSE 反向代理兼容**：Nginx 默认会缓冲 SSE，需关闭 `proxy_buffering off`；Cloudflare 默认支持但需在 Transform Rules 放行 `/mcp/sse`。
- **长连接生命周期**：MCP 长连接可能被 Aily 侧断开（30 分钟无活动），平台需 `sse-starlette` 的 ping/keepalive（默认 15s）+ 重连后能恢复（无状态设计，无需 session 持久化）。
- **返回值 2 万字**：现有 `submit_transcript` 返回 segments 全文已超 2 万字 → MCP 版本**必须精简**（D4 设计）。
- **`x-aily-user` 伪造**：未配 IP 白名单时任何人可冒用他人身份 → 必须先用 IP 白名单（运维脚本 `check_aily_ip_allowlist.py` 提醒）。
- **mcp tool 注册名冲突**：Aily 后台已有同名工具时注册失败 → manifest 用 `labmemory_` 前缀（`labmemory_submit_transcript`）。

## 验证策略

- 单元：`tests/test_mcp_server.py` 覆盖 10 个工具的入参/出参 schema、鉴权失败、`x-aily-user` 解析、降级路径。
- 集成：`scripts/smoke_aily_mcp.sh` 用 `curl -N` 模拟 SSE 连接，依次调 10 个工具，验证端到端。
- 端到端：用户手动在 Aily 工作助手注册 MCP URL，复制 Skill 提示词，跑通「会议 → 决策 → 任务」最小场景。
- 安全：`check_aily_ip_allowlist.py` + Nginx 配置 diff。