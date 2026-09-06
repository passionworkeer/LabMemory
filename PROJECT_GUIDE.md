# LabMemory｜晶研智流 · 项目使用与链路指南

> 本文件是项目**当前态**（合并队友分支 → A/B 计划 → 对抗审查 Tier1/Tier2 全部完成）的权威指南：能做什么、数据怎么流、怎么跑起来用。
> 配套文档：[`README.md`](./README.md)（项目背景）、[`INTEGRATION.md`](./INTEGRATION.md)（整合运维/技术细节）、[`AUDIT.md`](./AUDIT.md)（对抗审查与卖点实现度）、[`openspec/specs/`](./openspec/specs/)（冻结规格）。

---

## 1. 一句话定位

**嵌入飞书的可信实验决策与记忆系统**：把飞书会议中的科学讨论，编译为可审核、可版本化的实验决策——让每条参数有证据、每次执行用对版本、每个结果反向校正知识。不重做会议摘要，也不替代 ELN/LIMS，而是建立「会议判断 → 参数版本 → 实验执行 → 结果验证 → 知识复用」的**可信决策记忆层**。

---

## 2. 当前能力总览（已实现，对照代码）

| 支柱 | 能力 | 实现位置 |
|---|---|---|
| **会议决策编译** | 妙记/文本 → Aily 编译 → 结构化候选（参数/主张/证据/风险/任务） | `feishu-orchestrator/adapters/aily_adapter.py` |
| **可信实验记忆** | 主张以 `replaces` 关系版本化、历史永留；六道闸门决定能否发布 | `app/services/trust_rules.py`、`app/api/meetings.py:_build_claim` |
| **实验护照** | 围绕实验编号统一展示会议/参数/任务/执行/结果/异常/知识 | `app/api/passport.py` |
| **行动前审计** | 实验启动前五项检查 → 通过/需确认/阻断三态 | `app/api/tasks.py:_run_checks` |

**可信决策内核（对抗审查 Tier2 已落地，规则源自 PRD §10/§13）：**

| 卖点 | 状态 | 实现 |
|---|---|---|
| 三值留痕（原始/AI/人工） | ✅ | `Meeting.raw_payload` + `Candidate.candidates` + `MeetingReview.modifications`（含 `reason`） |
| 版本不覆盖 | ✅ | `Claim.replaces_claim_id` + superseded；**按参数维度**跟踪版本（未变参数继承不升版） |
| 六道质量闸门（候选发布前） | ✅ | 对象/参数/证据/范围/状态/责任门；未过降级 `pending_supplement`/`pending_validation` |
| 行动前审计三态 | ✅ | `_run_checks` 五项检查 → passed/needs_confirmation/blocked |
| 非二元知识状态（5 态） | ✅ | supported / partially_supported / refuted / replaced / insufficient_evidence |
| 语义栅栏 | ✅ | 「可以试试/建议/可能/暂定」不生效为当前参数 |
| 冲突检测 | ✅ | 数值冲突（同 scope 同参不同值）冻结 + 闸门/审计复用覆盖 6 类 |
| 证据失效降级 | ✅ | 结构化校验；问答排除失效主张；发布守卫（URL 探活为后续增强） |
| 异常可降级不虚假成功 | ✅ | pipeline 返回 `submitted`（非 success）；失败发告警卡；幂等原子化 |

---

## 3. 架构与系统链路

### 3.1 两子系统 + 契约边界

```
飞书会议/妙记
     │
     ▼
┌──────────────────────────────┐
│  feishu-orchestrator (8080)  │   飞书侧编排与 AI 接入
│  · 妙记/事件接入 + 验签       │   默认 RUN_MODE=mock（限 localhost）
│  · Aily Skill 编译 + 确定性校验│
│  · 卡片/任务/多维表格/知识库   │
│  · 幂等(原子文件锁)+重试(分类) │
└──────────────┬───────────────┘
               │  契约（openspec/specs/contracts/spec.md，4 路由 + Bearer）
               │  ① POST /api/v1/meetings      注册 MeetingPackage
               │  ② POST /api/v1/candidates    提交 CandidatePackage
               │  ③ POST /api/v1/card/callback 转发卡片回调（嵌套信封）
               │  ④ POST /api/v1/task/status   回写飞书任务状态
               │  ⑤ GET  /api/v1/candidates/{id} 候选详情
               ▼
┌──────────────────────────────┐
│  labmemory-platform (8081)   │   自研可信决策平台
│  FastAPI + React + SQLite    │
│  · 六道闸门 + 冲突检测 (trust_rules) │
│  · 复核 → 主张/版本(per-param) → 任务│
│  · 行动前审计(五项) → 启动 → 结果   │
│  · 知识发布(5 态) + 失败边界卡      │
│  · 实验护照 + 会前研讨包 + 可信问答 │
└──────────────────────────────┘
```

### 3.2 主链路走查（妙记 → 知识发布）

```
1. 妙记生成事件 → 编排器 event_router → 状态 WAITING_MINUTES → MINUTES_READY
2. Pipeline:
   a. 取妙记 → 组装 MeetingPackage（归一化：meeting_id == source_object_id，metadata.experiment_id）
   b. POST /api/v1/meetings 注册会议到平台
   c. Aily 编译 → CandidatePackage（_rule_validate 确定性校验：候选边界强制、experiment_ref 格式、参数单位）
   d. POST /api/v1/candidates 提交（平台返 status=submitted + 待复核数）
   e. 发复核卡（最多 3 张）→ 状态 REVIEWING
3. 复核人在平台/卡片确认：
   - confirm_review / card_callback(approve) 跑【六道闸门 + 冲突检测】
   - 全过 → 主张 current（按参数维度版本化、旧主张 supersede）+ 生成任务草稿
   - 证据/语义未过 → pending_validation；对象/参数/范围/责任未过 → pending_supplement（不建任务）
   - 数值冲突 → 冻结发布
4. 行动前审计（任务执行前）：_run_checks 五项（版本/证据/审批/资源/失败边界）
   - passed → audited；needs_confirmation → 补审批/资源/知悉失败边界后重审；blocked → 一键修正为当前版本
5. 启动任务 → 执行 → 提交结果（submitted，每任务一条）
6. 发布知识（PI/Lead）：knowledge_status 5 态；部分支持附带失败边界卡 + 复验任务
7. 实验护照：按会议 ID 组织数据链、按实验 ID 组织时间线，任一结果可回溯到决策与原话
```

### 3.3 状态机（简）

| 对象 | 状态 |
|---|---|
| 会后复核 | `pending` → `processed`（confirmed / ended） |
| 主张 | `pending_supplement` / `pending_validation` / `current` → `superseded`；`knowledge_status` 独立：null/supported/partially_supported/refuted/replaced/insufficient_evidence |
| 任务 | `draft` → `audited`/`needs_confirmation`/`blocked` → `running` → `completed` |
| 行动审计 | `pending` → `passed` / `needs_confirmation` / `blocked` |
| 结果 | `submitted` → `published`；`frozen`（版本不匹配） |

---

## 4. 怎么使用

### 4.1 前置

| 项 | 要求 | 实测 |
|---|---|---|
| Python | ≥ 3.10（平台 `pyproject` 标 ≥3.12，源码 3.11 可跑） | 3.11.9 ✅ |
| Node.js | ≥ 18（前端 Vite6/React19） | 22 ✅ |
| 数据库 | 默认 SQLite，启动自动建表，**需先建 `data/` 目录** | ✅ |
| 端口 | 平台 8081、编排器 8080 | 空闲 |
| Docker（可选） | 本机 npm 不可用时用容器构建前端 | 29.5.2 ✅ |

### 4.2 安装

```bash
# 平台后端
pip install -r labmemory-platform/requirements.txt

# 前端（本机 npm 正常时）
cd labmemory-platform/frontend && npm install && npm run build
#   若本机 npm 崩溃（Exit handler never called），用 Docker 构建：
#   docker run --rm -v "$(pwd):/app" -w /app node:22-alpine sh -c "rm -f package-lock.json && npm install && npm run build"
#   （注：仓库已提交可用的 package-lock.json；早期损坏 lockfile 已修）

# 编排器（仅 python-dotenv）
pip install -r feishu-orchestrator/feishu-orchestrator/requirements.txt

# 配置
cp labmemory-platform/.env.example labmemory-platform/.env
mkdir -p labmemory-platform/data          # SQLite 落库目录（必须）
```

### 4.3 启动平台 + 演示数据

```bash
cd labmemory-platform
python -m uvicorn app.main:app --port 8081 --host 127.0.0.1   # 后台运行
python -m scripts.seed_demo                                     # 注入演示数据
python -m scripts.mock_feishu_push demo                         # （可选）推 4 个演示会议
```

**访问：**
- 前端 UI：http://localhost:8081 （构建后挂载 React UI；未构建回退登录占位）
- Swagger API 文档：http://localhost:8081/docs （仅开发环境；`APP_ENV=production` 时关闭 /docs /redoc /openapi.json）
- 健康检查：http://localhost:8081/health

**演示账号**（密码均 `123456`）：`pi` / `lead` / `executor` / `admin`
> 登录接口对同一「用户名+IP」连续 5 次失败将锁定 15 分钟（返回 429）。

### 4.4 两个 Demo 故事（评测样例）

**Demo 1 — 旧参数拦截（行动前审计阻断）**
- `80℃ v1`（主张 C001/会议 M001）已被 `70℃ v2`（主张 C003/会议 M002）替代；
- 证据：70℃ 收率 78% vs 80℃ 收率 72%；
- 新成员从旧纪要建 80℃ 任务时，行动前审计**阻断**，展示版本差异/证据包/影响范围，支持**一键修正为 70℃**。

**Demo 2 — 结果回流（非二元知识状态）**
- 65℃ 使转化率 63%→78%，但副产物 4%→9%；
- 系统更新决策为**「部分支持」**，生成失败边界卡（根因标注"假设"）+ 创建降到 0.8 eq 复验任务，而非简单标"成功"。

### 4.5 编排器（默认 Mock 模式，无需真飞书凭证）

```bash
cd feishu-orchestrator/feishu-orchestrator
python scripts/run_pipeline.py --demo      # 端到端 demo（妙记→Aily→提交平台→发卡片）
python scripts/health_check.py             # 11 项模块体检
python -m core.webhook_server             # 起 webhook（/webhook/event, /webhook/card, /health）
```

> 真实飞书联动需在 `config/env.example` 配真 `FEISHU_APP_ID/SECRET`、`AILY_API_KEY`、`PLATFORM_API_BASE` 并切 `RUN_MODE=real`；mock 模式限 localhost + 启动告警「验签已旁路」。

---

## 5. 跨侧联动现状

### 5.1 正向（飞书侧 → 平台）：✅ 已打通

`scripts/cross_side_check.py` 以编排器同款 `urllib` + `Authorization: Bearer` 直打平台 4 条契约路由，5/5 通过：

```
✓ POST /api/v1/candidates      status=submitted
✓ GET  /api/v1/candidates/{id} 扁平候选 + meeting_title 富化
✓ POST /api/v1/card/callback   approve → 六道闸门 → 任务草稿（或 blocked 带报告）
✓ POST /api/v1/task/status     回写 feishu_task_guid
```

### 5.2 反向（平台 → 飞书侧）：新架构由 Aily 主动发卡

**新架构（v1.0.8 起）**：平台→飞书的"最后一公里"由 **Aily 主动完成**，
不依赖平台 webhook 推回。

- 平台内部触发 5 类事件（`decision.pending` / `preflight.blocked` /
  `execution.deviated` / `knowledge.ready` / `reverify.due`）
- Aily 在调完对应 MCP 工具后,按新 skill [`LabMemory 决策记忆/labmemory-decision-memory/SKILL.md`](./LabMemory%20%E5%86%B3%E7%AD%96%E8%AE%B0%E5%BF%86/labmemory-decision-memory/SKILL.md)
  「关键环节推送卡片」章节的模板,用 `lark-cli im +messages-send --as bot` 发对应飞书交互卡片
- 状态轮询(后半段链路感知)由 Aily 的 interval 自动化驱动,
  调 `/api/control-tower` + `/api/meetings` 拉状态,按 diff 续推后续步骤

**平台 webhook 协议(备用通道)**：平台代码层 5 类事件 webhook 实现仍在
（`app/services/aily_webhook.py`,见 [`docs/aily-skill/webhook-payload.md`](./docs/aily-skill/webhook-payload.md)）,
但新架构不依赖。历史背景:`FeishuActionRequest` 契约两侧未实现,正向流程已覆盖建任务,
详见 `INTEGRATION.md §6.4`。

---

## 6. 配置项速查

**平台 `.env`**（`labmemory-platform/`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/labmemory.db` | SQLite；可切 postgresql |
| `SERVER_PORT` | `8081` | 平台端口 |
| `PLATFORM_API_KEY` | `dev-...rotate` | 编排器调 `/api/v1/*` 鉴权（**生产必改**，启动告警） |
| `JWT_SECRET` | `dev-...rotate` | 用户 JWT 签名（**生产必改**，启动告警） |
| `CORS_ORIGINS` | `localhost:5173,8081` | 白名单；含 `*` 则强制禁 credentials |
| `FEISHU_ORCHESTRATOR_MODE` | `mock` | 平台→编排器方向（mock 不真调） |

**编排器 `config/env.example`**：

| 变量 | 默认 | 说明 |
|---|---|---|
| `RUN_MODE` | `mock` | real/mock；mock 限 localhost + 验签旁路告警 |
| `PLATFORM_API_BASE` | `https://labmemory.example.com/api` | 平台基址（含 /api） |
| `PLATFORM_API_KEY` | — | 与平台 PLATFORM_API_KEY 一致 |
| `LABMEMORY_EXPERIMENT_ID` | `EXP-DEMO-001` | 会议归属实验（生产按映射解析） |
| `FEISHU_APP_ID/SECRET`、`AILY_API_KEY` | 占位 | 真飞书实时联动必需 |

---

## 7. 测试命令一览

| 测试 | 命令 | 工作目录 | 说明 |
|---|---|---|---|
| 平台 14+ 步全链路 | `python -m scripts.e2e_test` | `labmemory-platform` | 需起服务 + seed；覆盖复核→审计→任务→结果→发布→护照 |
| 平台单测 | `python -m pytest tests/ -q` | `labmemory-platform` | TestClient，无需起服务 |
| 真跨侧联动 | `python -m scripts.cross_side_check` | `labmemory-platform` | 需起服务 + seed；编排器同款客户端打 4 路由 |
| 演示推送 | `python -m scripts.mock_feishu_push demo` | `labmemory-platform` | 模拟编排器推 4 会议 |
| 重置演示 | `python -m scripts.reset_demo` | `labmemory-platform` | 清库重注入 |
| 编排器集成 | `python tests/test_integration.py` | `feishu-orchestrator/feishu-orchestrator` | 22 测试，7 类（重跑前清 `data/`） |
| 编排器体检 | `python scripts/health_check.py` | 同上 | 11 项 |
| OpenSpec 校验 | `openspec validate --all` | 仓库根 | 全规格 + 活跃 change |

**当前实测**：平台 e2e 17 步、pytest、cross_side 5/5、编排器 22/22、`openspec validate --all` 17/17、活跃 change 归零——全绿。

---

## 8. 规格与开发流程（OpenSpec）

项目**强制 OpenSpec 规范驱动**（`CLAUDE.md` 第 0 节）：任何系统行为变更必须先建 change 提案 → `validate` → 实现 → `archive`（增量规格合入源真相）。

- 源真相：`openspec/specs/`（17 领域规格，含 contracts/trust-rules/platform-intake/decision-inbox/result-backflow 等）
- 变更闭环：`openspec/changes/archive/`（已归档 12 个 change，含本次整合/审查/Tier2 的 7 个）
- 常用：`openspec list` / `openspec validate --all` / `openspec archive <change> --yes`

---

## 9. 已知边界（诚实声明）

- **真飞书实时联调**：`FEISHU_*`/`AILY_*` 凭证为占位；真飞书事件→webhook→建任务链路需配真凭证并切 `RUN_MODE=real`。
- **证据 URL 可达性探活**：demo 用占位 URL，证据校验为结构化（非空+含 text）；真 URL 探活需飞书文档权限。
- **多 worker 分布式幂等**：本次单进程原子文件锁；多 worker 部署需 DB 唯一约束或分布式锁。
- **反向联动（平台→飞书）**：未实现（正向已覆盖建任务），按需启动。
- **数据性质**：全部为脱敏模拟数据，不代表真实业务收益；评测指标样例见 `README §7`。

---

## 10. 仓库结构

```
.
├── README.md                  # 项目背景/定位/团队
├── PROJECT_GUIDE.md           # 本文件（当前态功能/链路/使用）
├── INTEGRATION.md             # 整合运维/技术细节/跨侧现状
├── AUDIT.md                   # 对抗审查与卖点实现度
├── CLAUDE.md                  # 开发规范（OpenSpec 强制）
├── openspec/                  # 规格源真相 + 变更闭环（两子系统共用）
│   ├── specs/                 # 17 领域规格
│   └── changes/archive/       # 已归档 change
├── feishu-orchestrator/       # 飞书侧编排与 AI 接入（韩广宁）
│   └── feishu-orchestrator/{adapters,core,reliability,contracts,mock,scripts,tests}
├── labmemory-platform/        # 自研可信决策平台（林俊衡）
│   ├── app/{api,services,contracts,core,db,static}  # services/trust_rules.py + evidence.py 为可信内核
│   ├── frontend/              # React 19 + Vite 6 + Tailwind 4
│   ├── scripts/{seed_demo,e2e_test,mock_feishu_push,cross_side_check,reset_demo}
│   └── tests/
└── 附件/                       # PRD/角色说明/模拟数据/海选演示原型
```

---

## 11. 从零到一的演进（本项目已完成的里程碑）

1. **合并**：队友 `labmemory-platform` 分支 fast-forward 并入 main（零冲突）。
2. **A 计划**：两侧各自端到端跑通（平台 17 步 e2e + pytest、编排器 22 测试 + 11 体检），整合交付文档落地。
3. **B 计划**：平台拉回契约合规（鉴权双接受、`/api/v1` 前缀、3 条新路由 + `feishu_task_guid`），正向跨侧联动打通（`cross_side_check` 5/5）。
4. **对抗审查 Tier1**：~28 条有界缺陷全修（安全/越权/迁移/幂等原子化/虚假成功/编排器 real 模式会议注册），走 OpenSpec 归档。
5. **对抗审查 Tier2**：八大核心卖点从「PPT」落地为代码（六道闸门/冲突检测/语义栅栏/知识 5 态/证据降级/三值留痕/参数级版本/pipeline 诚实 status），规则源自 PRD §10/§13，走 4 个 OpenSpec change 归档。

> 当前态：规格自洽、两侧可用、跨侧打通、可信决策内核落地，全部推送 origin/main。
