# aily-mcp-server Specification Delta

## ADDED Requirements

### Requirement: MCP Server 同进程挂载

平台 SHALL 在 `labmemory-platform` 同进程内 mount 一个标准 MCP Server，路径 `/mcp/sse`（可由 `MCP_SSE_PATH` 配置），与现有 HTTP `/v1/*` 路由并存。MCP Server MUST NOT 替换或修改 HTTP `/v1/*` 契约，二者为并存入口。

#### Scenario: SSE 端点可访问
- GIVEN 平台 FastAPI 服务正常运行
- WHEN 客户端请求 `GET /mcp/sse`
- THEN 系统 SHALL 返回 SSE 流（含 `event: endpoint` 与 `endpoint: /mcp/messages`）并接受后续 MCP 工具调用

#### Scenario: 与 HTTP /v1 共存
- GIVEN MCP Server 与 HTTP `/v1/*` 同时启用
- WHEN 客户端分别请求 `/mcp/sse` 与 `/v1/transcripts`
- THEN 系统 SHALL 同时响应两条路径，互不影响

### Requirement: MCP 鉴权

平台 SHALL 在 SSE 连接升级与每次工具调用时校验 `Authorization: Bearer {PLATFORM_API_KEY}`（兼容 `X-Platform-Api-Key`），复用现有 `verify_platform_api_key`。鉴权失败 MUST 返回 403 且 MUST NOT 处理请求。

#### Scenario: Bearer 通过
- GIVEN Aily 以 `Authorization: Bearer {PLATFORM_API_KEY}` 建立 SSE 连接
- WHEN 平台校验
- THEN 系统 SHALL 升级 SSE 连接并接受后续工具调用

#### Scenario: 缺鉴权被拒
- GIVEN 请求未携带有效 Bearer
- WHEN 平台校验
- THEN 系统 SHALL 返回 403 且关闭连接

### Requirement: Aily 用户身份识别

平台 SHALL 从每次 MCP 工具调用的请求头读取 `x-aily-user`（Feishu `user_id`），用 `_resolve_actor` 解析为平台 `User`。解析失败 MUST 回退 PI（与 HTTP `/v1/*` 一致）。

#### Scenario: 合法 x-aily-user 命中
- GIVEN Aily 携带 `x-aily-user: ou_xxx`，且平台存在对应 `User.feishu_user_id`
- WHEN 工具调用解析 actor
- THEN 系统 SHALL 注入该 User 作为 reviewer/executor/publisher 等责任字段

#### Scenario: 未识别用户回退 PI
- GIVEN `x-aily-user` 不在平台 User 表中
- WHEN 工具调用解析 actor
- THEN 系统 SHALL 回退 PI 用户，保证责任门可过；审计日志记录 `aily_user_unresolved=true`

### Requirement: 10 个 MCP 工具

平台 SHALL 通过 MCP Server 暴露以下 10 个工具，每个 MUST 对应现有 HTTP `/v1/*` 入站接口的语义并复用同一业务内核：

| 工具名 | 对应 HTTP 接口 | Aily 用途 |
|---|---|---|
| `labmemory_submit_transcript` | `POST /v1/transcripts` | 收妙记/逐字稿 |
| `labmemory_submit_extraction` | `POST /v1/extractions` | 抽取结果回写 |
| `labmemory_create_review` | `POST /v1/decision-inbox` | 建复核项 |
| `labmemory_submit_verdict` | `POST /v1/decision-inbox/{id}/verdict` | 提交 pass/reject |
| `labmemory_issue_version` | `POST /v1/parameter-versions` | 签发参数版本 |
| `labmemory_preflight_check` | `POST /v1/preflight` | 执行前自检 |
| `labmemory_submit_execution` | `POST /v1/executions` | 回写执行结果 |
| `labmemory_update_passport` | `PATCH /v1/passports/{id}` | 更新护照/主张 |
| `labmemory_publish_knowledge` | `POST /v1/knowledge` | 发布知识 |
| `labmemory_create_reverify` | `POST /v1/reverify-tasks` | 复验任务 |

#### Scenario: 工具发现
- GIVEN Aily 已注册 MCP URL 并完成握手
- WHEN Aily 调用 `tools/list`
- THEN 系统 SHALL 返回上述 10 个工具的完整 manifest（name / description / inputSchema）

#### Scenario: 工具调用走 HTTP 等价路径
- GIVEN Aily 调用 `tools/call` 任一工具
- WHEN 平台处理
- THEN 系统 SHALL 走与对应 HTTP `/v1/*` 接口**等价**的业务逻辑（六道闸门 / 主张 / 任务 / 审计 / 结果 / 护照）

### Requirement: 返回值精简（≤2 万字）

MCP 工具返回值 SHALL 保持精简，遵守 Aily「2 万字以内」约束。全文 SHALL 通过返回值中的 `jump_url` 暴露，Aily 模型按需跳转到平台详情页。

#### Scenario: submit_transcript 精简返回
- GIVEN Aily 提交带 N 段 transcript 的会议
- WHEN 平台处理
- THEN 系统 SHALL 返回 `{transcript_id, meeting_id, segment_count, duration_sec, jump_url}`，**不包含 segments 全文**

#### Scenario: 含 jump_url
- GIVEN 任意 MCP 工具调用返回
- WHEN 平台生成响应
- THEN 响应 MUST 包含 `jump_url` 字段指向平台前端详情页（与 HTTP `/v1/*` 一致）

### Requirement: SSE 长连接与重连

平台 SHALL 在 SSE 长连接空闲超过 15 秒时发送心跳 `event: ping`，Aily 侧断开后能再次建立新连接而无需服务端持久化 session 状态。

#### Scenario: 心跳保活
- GIVEN SSE 连接空闲 15 秒
- WHEN 平台检测到空闲
- THEN 系统 SHALL 发送 `event: ping` 帧保持连接

#### Scenario: 重新连接
- GIVEN Aily 断开 SSE 连接
- WHEN Aily 重新发起连接
- THEN 系统 SHALL 接受新连接并正常处理工具调用，无状态泄漏

### Requirement: 部署安全（出口 IP 白名单）

平台部署方 SHALL 在反向代理/云防火墙层把 Aily 出口 IP 加入白名单：`101.126.59.88-92` 与 `122.14.241.34-38` 共 8 个 IP。未在白名单内的请求来源 MUST NOT 信任 `x-aily-user` 头，强制回退 PI 兜底。

#### Scenario: 白名单内来源信任 x-aily-user
- GIVEN 请求来自白名单 IP 且携带 `x-aily-user`
- WHEN 平台解析 actor
- THEN 系统 SHALL 信任该 header 解析为对应 User

#### Scenario: 白名单外来源忽略 x-aily-user
- GIVEN 请求来自非白名单 IP 且携带 `x-aily-user`
- WHEN 平台解析 actor
- THEN 系统 SHALL 忽略该 header，强制回退 PI；审计日志记录 `aily_user_untrusted_source=true`

### Requirement: MCP Server 工具 manifest 导出

平台 SHALL 在 `app/mcp_server/manifest.py` 导出 10 个工具的完整 manifest，含 name / description / inputSchema / annotations，供 Aily 后台「自定义工具」配置或文档归档使用。

#### Scenario: manifest 文件可读
- GIVEN 平台代码已部署
- WHEN 运维读取 `app/mcp_server/manifest.py` 或运行 `python -c "from app.mcp_server.manifest import MANIFEST; import json; print(json.dumps(MANIFEST, ensure_ascii=False, indent=2))"`
- THEN 系统 SHALL 输出合法 JSON manifest，含 10 个工具完整定义

### Requirement: MCP 端点路径可配置

平台 SHALL 支持通过 `MCP_SSE_PATH`（默认 `/mcp/sse`）与 `MCP_MESSAGES_PATH`（默认 `/mcp/messages`）自定义 SSE 端点与消息端点路径，便于运维加入随机 token 防扫描。

#### Scenario: 自定义路径生效
- GIVEN 部署配置 `MCP_SSE_PATH=/mcp/sse/<random>`
- WHEN 客户端请求该路径
- THEN 系统 SHALL 在该路径接受 SSE 连接；其他路径 MUST NOT 接受

### Requirement: Skill 提示词与工具文档配套交付

平台 SHALL 在仓库根 `docs/aily-skill/` 下交付：
- `skill-prompt.md`：单 Skill《LabMemory 决策记忆》系统提示词（中文，覆盖 12 步链路、工具调用顺序、参数模板、失败降级）。
- `tools-manifest.json`：10 个工具的 JSON manifest，可一键导入 Aily 后台。
- `webhook-payload.md`：5 类出站 webhook payload schema + 验签方式 + 接入指引。
- 仓库根 `AILY_MCP.md`：Aily 侧接入步骤（生成 SSE URL、注册、粘贴 Skill）。

#### Scenario: 文档存在且可读
- GIVEN 实施完成
- WHEN 团队成员读取 `docs/aily-skill/` 与 `AILY_MCP.md`
- THEN 系统 SHALL 提供完整的接入指引，无需查询外部资源