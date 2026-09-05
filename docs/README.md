# LabMemory 文档索引

> 本目录是 LabMemory 仓库的**完整文档地图**。从根 [`README.md`](../README.md) 进来后，按需查这里。

---

## 0. 按角色找文档

| 我是… | 先看 |
|---|---|
| 评委 / 业务方 | [`README.md`](../README.md) → [`参赛方案文档.md`](../参赛方案文档.md) |
| 新加入的开发者 | [`README.md`](../README.md) → [`PROJECT_GUIDE.md`](../PROJECT_GUIDE.md) → [`docs/infrastructure/deployment.md`](infrastructure/deployment.md) |
| 运维 / 部署 | [`INTEGRATION.md`](../INTEGRATION.md) → [`docs/infrastructure/servers.md`](infrastructure/servers.md) → [`docs/operations/runbook.md`](operations/runbook.md) |
| 飞书 / Aily 集成方 | [`AILY_INTEGRATION.md`](../AILY_INTEGRATION.md) → [`AILY_MCP.md`](../AILY_MCP.md) → [`api-meetings-integration.md`](api-meetings-integration.md) |
| 安全 / 合规审核 | [`AUDIT.md`](../AUDIT.md) |
| 规格作者 / 治理 | [`../CLAUDE.md`](../CLAUDE.md) → [`../openspec/specs/`](../openspec/specs/) |

---

## 1. 根目录文档（仓库级）

| 文件 | 用途 |
|---|---|
| [`README.md`](../README.md) | **项目入口**：一句话定位、快速开始、文档地图 |
| [`PROJECT_GUIDE.md`](../PROJECT_GUIDE.md) | 当前能力总览、架构与数据链路、卖点实现度 |
| [`INTEGRATION.md`](../INTEGRATION.md) | 两子系统整合运维、跨侧联动、契约路由、配置项、启动脚本 |
| [`AUDIT.md`](../AUDIT.md) | 对抗性 + 第一性原理审查、Tier 1 已修、Tier 2 路线图、卖点实现度 |
| [`AILY_INTEGRATION.md`](../AILY_INTEGRATION.md) | 平台 ↔ Aily 接口口径（10 个入站接口、Webhook 出站） |
| [`AILY_MCP.md`](../AILY_MCP.md) | MCP 接入指南、SSE 协议、鉴权（Bearer + URL queryParam）、10 个工具 |
| [`参赛方案文档.md`](../参赛方案文档.md) | 完整参赛方案（产品/技术/团队/价值） |
| [`CLAUDE.md`](../CLAUDE.md) | **强制开发规范**（OpenSpec 工作流、规格优先、红线） |

---

## 2. 本目录（docs/）

### 2.1 `infrastructure/` — 服务器与部署
| 文件 | 用途 |
|---|---|
| [`infrastructure/servers.md`](infrastructure/servers.md) | **生产服务器档案**（地址、配置、服务现状、最近一次体检） |
| [`infrastructure/deployment.md`](infrastructure/deployment.md) | 部署前 / 中 / 后 checklist，平台/编排器启动顺序 |

### 2.2 `operations/` — 运维 runbook
| 文件 | 用途 |
|---|---|
| [`operations/runbook.md`](operations/runbook.md) | 备份策略、健康检查、故障应急、证书续期、SSH 凭据 |

### 2.3 `aily-skill/` — Aily 技能
| 文件 | 用途 |
|---|---|
| [`aily-skill/skill-prompt.md`](aily-skill/skill-prompt.md) | Aily Skill 提示词（让 Aily 学会调用平台 10 个工具） |
| [`aily-skill/webhook-payload.md`](aily-skill/webhook-payload.md) | Webhook 出站 payload 契约 |
| [`aily-skill/tools-manifest.json`](aily-skill/tools-manifest.json) | MCP 工具清单（自检用） |

### 2.4 平台 API
| 文件 | 用途 |
|---|---|
| [`api-meetings-integration.md`](api-meetings-integration.md) | 飞书会议集成（事件订阅、妙记拉取、回调路由） |
| [`platform-intake-api.md`](platform-intake-api.md) | 平台 intake 接口（会议/候选/复核/任务/结果完整字段） |

---

## 3. 子模块文档

### 3.1 飞书编排子系统
| 文件 | 用途 |
|---|---|
| [`../feishu-orchestrator/feishu-orchestrator/README.md`](../feishu-orchestrator/feishu-orchestrator/README.md) | 子系统导览（架构、运行模式、可靠性） |
| [`../feishu-orchestrator/feishu-orchestrator/DEPLOYMENT.md`](../feishu-orchestrator/feishu-orchestrator/DEPLOYMENT.md) | 飞书 CLI 配置、Real/Mock 模式、部署步骤 |

### 3.2 自研平台子系统
| 文件 | 用途 |
|---|---|
| [`../labmemory-platform/README.md`](../labmemory-platform/README.md) | 平台核心规则、状态机、目录结构、环境要求 |
| [`../labmemory-platform/deploy/README.md`](../labmemory-platform/deploy/README.md) | 反向代理（Nginx / Cloudflare Tunnel）配置 + 部署前 checklist |
| [`../labmemory-platform/deploy/nginx-labmemory-mcp.conf`](../labmemory-platform/deploy/nginx-labmemory-mcp.conf) | Nginx 站点配置片段（直 copy 进 server 块） |
| [`../labmemory-platform/deploy/cloudflared-config.yml`](../labmemory-platform/deploy/cloudflared-config.yml) | Cloudflare Tunnel 接入配置 |

---

## 4. 冻结规格（OpenSpec）

`../openspec/specs/` 按领域拆分的**当前事实**：

| 规格 | 内容 |
|---|---|
| `meeting-ingest/` | 妙记/事件接入、逐字稿、证据分段 |
| `decision-compiler/` | Aily 决策编译、候选对象、语义分类 |
| `decision-inbox/` | 决策收件箱、三值留痕、发布闸门 |
| `trust-rules/` | 六道闸门、主张/参数/任务状态机、冲突检测 |
| `action-audit/` | 行动前审计五类检查、版本替代、一键修正 |
| `result-backflow/` | 结果回流、知识状态、失败边界卡 |
| `feishu-actions/` | 卡片下发、任务创建、协同看板与知识文档回流 |
| `orchestration-reliability/` | 编排状态机、幂等、重试退避、运行模式隔离 |
| `contracts/` | `MeetingPackage` / `CandidatePackage` / `FeishuActionRequest` / `CardCallback` 接口契约 |

`../openspec/changes/` 当前进行中的变更提案 + 已归档的历史。

---

## 5. 文档维护约定

- **根 README**：项目入口，唯一对外门面。新人/评委/合作方从这里进。
- **docs/**：所有细节文档的"家"。新文档优先放在这里。
- **子模块 README**：只在子模块内部消费，不在根 README 重复全文。
- **OpenSpec**：接口契约、状态机、规则——任何影响系统行为的变更，**先走 OpenSpec change**，再更新代码。
- **每次归档 change**：顺手检查相关文档是否需要同步更新（特别是根 README 和本索引）。