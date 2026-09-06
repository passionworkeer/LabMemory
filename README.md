# LabMemory｜晶研智流

> **嵌入飞书的可信实验决策与记忆系统** — 把飞书会议中的科学讨论，编译为可审核、可版本化的实验决策。让每条参数有证据、每次执行用对版本、每个结果反向校正知识。

---

## 0. 项目信息

| 项 | 内容 |
|---|---|
| 赛事 | AI 先锋未来人才大赛 2026（飞书比赛） |
| 队伍 | 溯研 LabTrace |
| 产品 / 可信记忆负责人 | 王健俊 |
| 飞书侧编排与 AI 接入负责人 | 韩广宁 |
| 自研平台与可信决策系统负责人 | 林俊衡 |
| 文档版本 | PRD V1.0（复赛可运行 Demo / 受控试点设计） |
| 数据性质 | **全部为脱敏模拟数据，不代表晶泰科技真实业务数据** |
| 仓库性质 | 私有仓库，仅队伍内部使用 |

---

## 1. 一句话现状

两个子系统（**feishu-orchestrator** 飞书侧 + **labmemory-platform** 自研平台）已并入同一仓库，**两侧各自端到端跑通**，**正向跨侧联动已打通**（`scripts/cross_side_check` 5/5）。Aily 通过 MCP 通道直连平台的 10 个可信决策工具。详细实现度见 [`AUDIT.md`](./AUDIT.md)。

---

## 2. 五大支柱

| 支柱 | 核心能力 | 用户价值 |
|---|---|---|
| **会议决策编译器** | 妙记 → 候选参数/主张/证据/风险/任务 | 不再靠人工从长纪要里找"到底决定了什么" |
| **可信实验记忆** | 主张—证据—版本—状态—范围—责任六道闸门 | 结论可追溯、可更新，旧版本不静默覆盖 |
| **实验护照** | 围绕实验编号统一展示会议/参数/任务/执行/结果 | 任一结果都能回到决策与原话 |
| **行动前审计** | 实验启动前五项检查 → 通过/需确认/阻断三态 | 在错误知识进入实验前阻断，而非事后复盘 |
| **可信决策内核** | 六道闸门 + 冲突检测 + 证据失效降级 + 三值留痕 + 5 态知识状态 | 卖点从 spec 落到代码（详见 [§6](#6-核心卖点实现度)） |

---

## 3. 文档地图

> **新人从这里进**：先看 [§4 快速开始](#4-快速开始)，再按角色查下表。

### 3.1 按角色

| 我是… | 先看 |
|---|---|
| 评委 / 业务方 | [`参赛方案文档.md`](./参赛方案文档.md) → [`PROJECT_GUIDE.md`](./PROJECT_GUIDE.md) §2 |
| 新加入的开发者 | [`PROJECT_GUIDE.md`](./PROJECT_GUIDE.md) → [`INTEGRATION.md`](./INTEGRATION.md) → [`docs/README.md`](./docs/README.md) |
| 运维 / 部署 | [`docs/infrastructure/servers.md`](./docs/infrastructure/servers.md) → [`docs/operations/runbook.md`](./docs/operations/runbook.md) |
| 飞书 / Aily 集成方 | [`AILY_INTEGRATION.md`](./AILY_INTEGRATION.md) → [`AILY_MCP.md`](./AILY_MCP.md) |
| 安全 / 合规审核 | [`AUDIT.md`](./AUDIT.md) |
| 规格作者 | [`CLAUDE.md`](./CLAUDE.md) → [`openspec/specs/`](./openspec/specs/) |

### 3.2 完整索引

详见 [`docs/README.md`](./docs/README.md)。

### 3.3 仓库根文档

| 文件 | 用途 |
|---|---|
| [`PROJECT_GUIDE.md`](./PROJECT_GUIDE.md) | **当前态**：能做什么、数据怎么流、怎么用 |
| [`INTEGRATION.md`](./INTEGRATION.md) | 整合运维、跨侧联动、契约路由、配置项、启动脚本 |
| [`AUDIT.md`](./AUDIT.md) | 对抗性 + 第一性原理审查、Tier 1 已修、Tier 2 路线图 |
| [`AILY_INTEGRATION.md`](./AILY_INTEGRATION.md) | 平台 ↔ Aily 接口口径（10 入站 + Webhook 出站） |
| [`AILY_MCP.md`](./AILY_MCP.md) | MCP 接入指南、SSE 协议、鉴权、10 工具 |
| [`参赛方案文档.md`](./参赛方案文档.md) | 完整参赛方案（产品/技术/团队/价值） |
| [`CLAUDE.md`](./CLAUDE.md) | **强制开发规范**（OpenSpec 工作流） |

---

## 4. 快速开始

### 4.1 三分钟跑起来（本地开发）

```bash
# 1. 装后端依赖
pip install -r labmemory-platform/requirements.txt

# 2. 构建前端
cd labmemory-platform/frontend && npm install && npm run build && cd -

# 3. 起平台（默认 :8081，SQLite 落本地 data/）
cd labmemory-platform
mkdir -p data
python -m uvicorn app.main:app --port 8081 --host 127.0.0.1

# 4. 注入演示账号 + 项目 + 实验 + 端到端场景
python -m scripts.seed_demo

# 5. 推 4 个演示会议（可选）
python -m scripts.mock_feishu_push demo
```

访问：
- 前端 UI：http://localhost:8081
- Swagger：http://localhost:8081/docs
- 健康：http://localhost:8081/health

演示账号（密码 `123456`）：`pi` / `lead` / `executor` / `admin`

### 4.2 飞书侧编排（默认 Mock 模式，无需真凭证）

```bash
cd feishu-orchestrator/feishu-orchestrator
pip install -r requirements.txt
python scripts/run_pipeline.py --demo    # 端到端 demo
python -m core.webhook_server            # 起 webhook 服务（:8080）
```

### 4.3 跑测试

```bash
cd labmemory-platform && pytest -q                          # 平台 e2e
cd feishu-orchestrator/feishu-orchestrator && bash scripts/cross_side_check.sh   # 跨侧 5/5
```

详细配置项见 [`INTEGRATION.md`](./INTEGRATION.md) §2.3。

---

## 5. 架构与系统链路

```
飞书会议/妙记
     │
     ▼
┌──────────────────────────────┐
│  feishu-orchestrator (8080)  │   飞书侧编排与 AI 接入
│  · 妙记/事件接入 + 验签       │   负责人：韩广宁
│  · Aily Skill 编译 + 校验    │
│  · 卡片/任务/多维表格/知识库   │
│  · 幂等(原子文件锁)+重试(分类) │
└──────────────┬───────────────┘
               │  契约（openspec/specs/contracts/）
               │  POST /api/v1/meetings | candidates | card/callback | task/status
               ▼
┌──────────────────────────────┐
│  labmemory-platform (8081)   │   自研可信决策平台
│  FastAPI + React + SQLite    │   负责人：林俊衡
│  · 会后复核 → 主张/版本      │
│  · 行动前审计（六道闸门）     │
│  · 任务执行 + 结果回流        │
│  · 知识发布 + 实验护照        │
└──────────────┬───────────────┘
               │  MCP SSE (10 tools) ─────► Aily 后台(主路径)
               │  Webhook ◄──────────────── 备用通道(新架构不依赖)
               ▼
         飞书卡片推送:Aily 主动发卡(最后一公里),不依赖平台 webhook
```

> **新主路径说明**：飞书侧走"Aily agent + MCP"直连平台 ——
> Aily 通过 `aily-mcp install-remote` 自助接入平台 MCP,事件自动化触发 10 步闭环,
> 5 类卡片由 Aily 用 `lark-cli im +messages-send --as bot` 主动发送。
> 平台 webhook 协议仍在(平台能力未删除),但新架构**不依赖** webhook 推回。
> 详细流程见新 skill [`LabMemory 决策记忆/labmemory-decision-memory/SKILL.md`](./LabMemory%20决策记忆/labmemory-decision-memory/SKILL.md)
> 与 [`AILY_INTEGRATION.md`](./AILY_INTEGRATION.md)。

详细架构与两个 Demo 故事见 [`PROJECT_GUIDE.md`](./PROJECT_GUIDE.md) §3。

---

## 6. 核心卖点实现度

> **TL;DR**：六道闸门、语义栅栏、冲突检测、知识状态 5 态、证据失效降级、三值留痕、按参数维度版本化——**全部落地**。详见 [`AUDIT.md`](./AUDIT.md) §3 与 [`PROJECT_GUIDE.md`](./PROJECT_GUIDE.md) §2。

| 卖点 | 状态 | 实现 |
|---|---|---|
| 三值留痕（含 reason） | ✅ | `MeetingReview.modifications` |
| 版本不覆盖（按参数维度） | ✅ | `Claim.replaces_claim_id` + superseded |
| 六道闸门（候选→主张） | ✅ | `app/services/trust_rules.py` |
| 行动前审计三态 | ✅ | `_run_checks` |
| 非二元知识状态 5 态 | ✅ | supported / partially_supported / refuted / replaced / insufficient_evidence |
| 语义栅栏（"可以试试"不生效） | ✅ | "可以试试/建议/可能/暂定" 关键词拒收 |
| 冲突检测（数值冲突冻结 + 6 类复用） | ✅ | 闸门/审计复用 |
| 证据失效降级 | ✅ | 结构化校验 + 问答排除 + 发布守卫 |
| 异常可降级不虚假成功 | ✅ | pipeline 返回 `submitted`，失败发告警卡 |

**仍待 Tier 2**：详情见 [`AUDIT.md`](./AUDIT.md) §3（10 条 P0/P1 缺失功能，需产品规则定义后另起 change）。

---

## 7. 生产服务器现状

**生产环境**：阿里云 Ubuntu-lrtz（<SERVER_IP>，Ubuntu 24.04，2 核 / 2 GiB / 40 GiB，域名 `<your-domain.com>`）

| 项 | 状态 |
|---|---|
| 平台服务 `labmemory-platform.service` | ✅ running（4 天 9 小时） |
| Nginx 80/443 | ⚠️ **443 证书加载失败**（admin 无权读 `/etc/letsencrypt/`，详见 [`docs/infrastructure/servers.md`](./docs/infrastructure/servers.md) §6.1） |
| 数据库每日备份 | ✅ 7 份在线备份保留 |
| ~~飞书编排服务 `:8080`~~ | n/a — **新架构不依赖** :8080 编排器（飞书侧走 Aily agent + MCP 直连平台） |
| 服务器 .git | ❌ 当前无 .git，部署走手工 rsync |

**下一步建议（按优先级）**：
1. 修 HTTPS 证书加载（影响 Aily 接入 + 飞书 webhook）
2. 服务器加 .git + deploy key，改走 git pull 部署
3. （可选）按需拉起 feishu-orchestrator（备用路径，详见 [`feishu-orchestrator/feishu-orchestrator/README.md`](./feishu-orchestrator/feishu-orchestrator/README.md)）
4. 加自动告警（备份/磁盘/进程）

完整现状 + 应急 SOP 见 [`docs/infrastructure/servers.md`](./docs/infrastructure/servers.md) 与 [`docs/operations/runbook.md`](./docs/operations/runbook.md)。

---

## 8. 仓库约定

- **OpenSpec 强制**：任何影响系统行为的变更，必须先创建 OpenSpec change（`openspec/changes/`），通过 `openspec validate` 再写代码。详见 [`CLAUDE.md`](./CLAUDE.md)。
- **接口契约优先**：涉及 `openspec/specs/contracts/` 的变更，先冻结契约再并行开发。
- **数据口径诚实**：文档与评测中涉及指标时，必须标注"脱敏模拟/原型样例"，不得冒充真实企业收益。
- **保密**：本仓库为私有；规格中不得写入真实妙记、Token、受限文档等内容。

---

## 9. 关联文档

- 完整文档索引：[`docs/README.md`](./docs/README.md)
- 部署 checklist：[`docs/infrastructure/deployment.md`](./docs/infrastructure/deployment.md)
- 运维 runbook：[`docs/operations/runbook.md`](./docs/operations/runbook.md)
- 服务器档案：[`docs/infrastructure/servers.md`](./docs/infrastructure/servers.md)
- 子模块：[`labmemory-platform/`](./labmemory-platform/) · [`feishu-orchestrator/`](./feishu-orchestrator/)