# LabMemory 整合交付文档（INTEGRATION）

> 本文件是飞书编排子系统（`feishu-orchestrator`）与自研平台子系统（`labmemory-platform`）合并到同一仓库后的**整合运维与技术说明**，面向团队与评委。
> 项目全貌见 [`README.md`](./README.md)；开发规范见 [`CLAUDE.md`](./CLAUDE.md)；接口契约见 [`openspec/specs/contracts/spec.md`](./openspec/specs/contracts/spec.md)。
>
> **架构说明**：飞书侧接入已切换为 **Aily agent + MCP `/mcp/sse`** 主路径。
> `feishu-orchestrator` 子系统作为**备用路径**(mock 演示 + 历史 fallback)保留，
> 完整接入流程见 [`AILY_INTEGRATION.md`](./AILY_INTEGRATION.md) 与新 skill
> [`LabMemory 决策记忆/labmemory-decision-memory/SKILL.md`](./LabMemory%20%E5%86%B3%E7%AD%96%E8%AE%B0%E5%BF%86/labmemory-decision-memory/SKILL.md)。

---

## 0. 一句话现状

**新主路径（v1.0.8 起）**：飞书侧走 **Aily agent + MCP `/mcp/sse`**——
Aily 自助接入平台 10 个 `labmemory_*` 工具,事件自动化触发 10 步闭环,
5 类卡片由 Aily 用 `lark-cli im +messages-send --as bot` 主动发送,状态轮询由 Aily interval 任务驱动。

**历史路径(备用)**：两个子系统(`feishu-orchestrator` + `labmemory-platform`)已并入同一仓库、
**两侧各自端到端跑通**(平台 17 步决策全链路 + pytest、编排器 22 个集成测试 + 11 项体检,全部绿);
**正向跨侧联动已打通**(`scripts/cross_side_check` 5/5 通过,见 §6.3)。
平台 webhook 反向通道(平台→飞书)代码层已落地但默认 `FEISHU_ORCHESTRATOR_MODE=mock` 不真调。
新主路径不依赖平台 webhook 反向通道,由 Aily 主动发卡替代。

---

## 1. 架构总览

```
新主路径(飞书侧):
飞书会议/妙记
     │
     ▼
┌──────────────────────────────┐
│  Aily 后台 (agent 模式)      │   飞书侧接入(v1.0.8 起)
│  · 事件自动化触发              │   负责人:韩广宁
│  · 调 MCP 10 个 labmemory_* 工具 │
│  · lark-cli 主动发 5 类卡片   │
│  · interval 状态轮询          │
└──────────────┬───────────────┘
               │  MCP SSE (POST /mcp/messages)
               │  鉴权:Bearer 或 ?token=
               ▼
┌──────────────────────────────┐
│  labmemory-platform (8081)   │   自研可信决策平台
│  FastAPI + React + SQLite    │   负责人:林俊衡
│  · 会后复核 → 主张/版本      │
│  · 行动前审计（六道闸门）     │
│  · 任务执行 + 结果回流        │
│  · 知识发布 + 实验护照        │
│  · 决策问答 / 会前研讨包      │
└──────────────────────────────┘

备用路径(feishu-orchestrator :8080,新架构不依赖,代码/mock 演示保留):
  飞书事件 → webhook → 编排器 → POST /api/v1/* → 平台
  平台 → POST /webhook/platform(FeishuActionRequest)→ 编排器 → 飞书
```

**新主路径数据流向**：妙记 → Aily 事件自动化 → Aily 调 MCP 10 步 → Aily 主动发卡片
（`lark-cli im +messages-send --as bot`）→ Aily interval 轮询 `/api/control-tower` 感知
平台侧操作完成 → 续推后续步骤。

**两个 Demo 故事**（对应 README 第 6 节）：
1. **旧参数拦截**：80℃ v1 被 70℃ v2 替代后，新成员建 80℃ 任务时行动前审计**阻断**，支持一键修正为 70℃。
2. **结果回流**：65℃ 使转化率 63%→78% 但副产物 4%→9%，决策更新为「部分支持」并生成失败边界卡 + 复验任务（非简单"成功"）。

---

## 2. 快速启动

### 2.1 前置

| 项 | 要求 | 本机实测 |
|---|---|---|
| Python | ≥ 3.10（平台 `pyproject` 标 ≥3.12，但源码 3.11 可跑，见 §5） | 3.11.9 ✅ |
| Node.js | ≥ 18（前端 Vite 6 / React 19） | 22.22.2 ✅ |
| 数据库 | 默认 SQLite，启动自动建表，**需先建 `data/` 目录** | ✅ |
| 端口 | 平台 8081 | 空闲 ✅ |
| ~~端口~~ | ~~编排器 8080(备用路径)~~ | n/a — 新主路径不依赖 |

### 2.2 装依赖

```bash
# 平台后端
pip install -r labmemory-platform/requirements.txt

# 前端（lockfile 曾损坏，已修复，见 §5；npm install + npm run build）
cd labmemory-platform/frontend && npm install && npm run build

# 编排器（仅 python-dotenv）
pip install -r feishu-orchestrator/feishu-orchestrator/requirements.txt
```

### 2.3 配置

```bash
cp labmemory-platform/.env.example labmemory-platform/.env   # 默认 dev key 即可跑
mkdir -p labmemory-platform/data                             # SQLite 落库目录（必须）
```

关键配置项（`.env`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/labmemory.db` | 默认 SQLite；可切 `postgresql://...` |
| `SERVER_PORT` | `8081` | 平台端口 |
| `PLATFORM_API_KEY` | `dev-platform-api-key-please-rotate` | **备用**:编排器调用 `/v1/*` 的鉴权 key(新主路径用同一 key 调 `/mcp/sse`) |
| `JWT_SECRET` | `dev-jwt-secret-please-rotate` | 平台用户 JWT 签名 |
| `FEISHU_ORCHESTRATOR_MODE` | `mock` | **备用**:平台→编排器方向(新主路径不依赖) |

### 2.4 起服务 + 演示数据

```bash
# 1) 起平台（后台）
cd labmemory-platform
python -m uvicorn app.main:app --port 8081 --host 127.0.0.1

# 2) 注入演示数据（账号/项目/实验/3 场景）
python -m scripts.seed_demo

# 3)（可选）推 4 个演示会议
python -m scripts.mock_feishu_push demo
```

访问：
- **前端 UI**：http://localhost:8081 （`frontend/dist/` 已构建时挂载真实 React UI；否则回退 `app/static/index.html` 登录占位）
- **Swagger 文档**：http://localhost:8081/docs
- **健康检查**：http://localhost:8081/health

**演示账号**（密码均为 `123456`）：`pi` / `lead` / `executor` / `admin`

### 2.5 编排器(备用路径,默认 Mock 模式,无需真飞书凭证)

> **⚠️ 新主路径不依赖本服务**。本节保留作为 mock 演示 / 历史 fallback 的参考。
> 飞书侧接入已切换为"Aily agent + MCP `/mcp/sse`",详见 [`AILY_INTEGRATION.md`](./AILY_INTEGRATION.md)。

```bash
cd feishu-orchestrator/feishu-orchestrator
python scripts/run_pipeline.py --demo     # 端到端 demo(妙记→Aily→提交平台→发卡片)
python scripts/health_check.py            # 11 项模块体检
python -m core.webhook_server            # 起 webhook 服务(/webhook/event, /webhook/card, /health)
```

> 真实飞书联动需在 `config/env.example` 配置真 `FEISHU_APP_ID/SECRET`、`AILY_API_KEY`、`PLATFORM_API_BASE` 并切 `RUN_MODE=real`。当前为占位符,故用 Mock。

---

## 3. 端到端验证（本次实测证据）

> 命令在仓库根执行；平台服务需先起（§2.4）。

### 3.1 平台：14+ 步决策全链路

```bash
cd labmemory-platform
python -m scripts.seed_demo        # 先注入数据
python -m scripts.e2e_test         # 全链路
python -m pytest tests/ -q         # TestClient 单测
```

**实测结果（2026-08-11，Python 3.11.9）**：

```
✓ health                          ✓ task.resources (ready)
✓ login (pi/lead/executor)        ✓ task.ack_failure_boundary
✓ ingest (meeting+candidate)      ✓ audit (passed)
✓ review.confirm (claim+task)     ✓ task.start (running)
✓ audit.first (needs_confirmation)✓ result.submit
✓ task.approve (approved)         ✓ result.publish (partially_supported)
✓ passport (5 meetings/17 events) ✓ permission.executor_cannot_publish (blocked)
✓ second_meeting (supersedes v1)  ✓ permission.pi_only_experiments (blocked)
✓ passport_after_second (6 meetings)
→ ✓ E2E 测试通过
pytest: 1 passed
```

这覆盖了**两个 Demo 故事的内核**：行动前审计三态（needs_confirmation → passed）、版本替代（second_meeting supersedes）、结果回流（partially_supported）、权限闸门（executor 不能发布、PI-only 实验管理）。

### 3.2 编排器：22 个集成测试

```bash
cd feishu-orchestrator/feishu-orchestrator
python tests/test_integration.py   # 自带 __main__，7 个测试类
```

**实测结果**：`22 个测试 / 通过 22 / 失败 0 / 错误 0`，含 7 类：事件路由与幂等、Aily 编译、平台集成（提交候选/卡片回调/任务状态）、卡片处理、可靠性（幂等/集成日志/状态机）、流水线端到端、webhook 验签（正/反/篡改/空密钥/过期/畸形）。

### 3.3 编排器：11 项模块体检

```bash
python scripts/health_check.py     # → 11 通过 / 0 失败
```

### 3.4 验收速查

| 闸门 | 命令 | 期望 | 实测 |
|---|---|---|---|
| 平台全链路 | `python -m scripts.e2e_test` | `✓ E2E 测试通过` | ✅ 17 步全过 |
| 平台单测 | `python -m pytest tests/ -q` | 全绿 | ✅ |
| 演示推送 | `python -m scripts.mock_feishu_push demo` | 4 场景无错 | ✅ |
| 平台健康 | `GET /health` | 200 `sqlite` | ✅ |
| 平台前端 | `GET /` | 200 | ✅（回退占位；dist 构建后为真实 UI） |
| 平台 API 文档 | `GET /docs` | 200 Swagger | ✅ |
| 编排器集成 | `python tests/test_integration.py` | 22/22 | ✅ |
| 编排器体检 | `python scripts/health_check.py` | 11/11 | ✅ |
| **真跨侧联动** | `python -m scripts.cross_side_check` | 5/5 | ✅（B 计划后新增） |

---

## 4. 两个子系统测试命令一览

| 子系统 | 命令 | 工作目录 | 说明 |
|---|---|---|---|
| 平台 e2e | `python -m scripts.e2e_test` | `labmemory-platform` | 需起服务；14+ 步真实 HTTP 链路 |
| 平台单测 | `python -m pytest tests/ -q` | `labmemory-platform` | TestClient，无需起服务 |
| 演示数据 | `python -m scripts.seed_demo` | `labmemory-platform` | 账号/项目/实验/3 场景 |
| 演示推送 | `python -m scripts.mock_feishu_push demo` | `labmemory-platform` | 模拟编排器推 4 会议 |
| 重置演示 | `python -m scripts.reset_demo` | `labmemory-platform` | 清库重注入 |
| 编排器集成 | `python tests/test_integration.py` | `feishu-orchestrator/feishu-orchestrator` | 7 类 22 测试 |
| 编排器体检 | `python scripts/health_check.py` | `feishu-orchestrator/feishu-orchestrator` | 11 项 |
| 编排器 demo | `python scripts/run_pipeline.py --demo` | `feishu-orchestrator/feishu-orchestrator` | 流水线烟测 |

---

## 5. 已知环境项（诚实声明）

| 项 | 现象 | 处置 |
|---|---|---|
| **Python 版本** | 平台 `pyproject.toml` 标 `requires-python>=3.12`，本机仅 3.11.9 | 用 `pip install -r requirements.txt` + 源码直跑 `uvicorn` 绕过 packaging 约束；实测 3.11.9 全链路通过。若用 `pip install <package>` 安装包本身会被 3.12 约束拒绝 |
| **SQLite 目录** | `DATABASE_URL=sqlite:///./data/labmemory.db`，平台不自动建 `data/` 目录 | 首次启动前 `mkdir -p labmemory-platform/data`，否则 `unable to open database file` |
| **Windows 控制台编码** | 默认 cp1252/gbk 会让中文 print 抛 `UnicodeEncodeError` | 设 `PYTHONIOENCODING=utf-8`（编排器 `core/config.py` 已在启动期强制重配） |
| **前端构建（已修复）** | 提交进来的 `frontend/package-lock.json` 内部不一致，导致 `npm install` 在**宿主机与干净 `node:22-alpine` 容器里同样**触发 `Exit handler never called!`（`node_modules` 装到中途崩溃、`.bin/tsc\|vite` 软链建不出、`npm run build` 报 `tsc 不是命令`）。早先误判为「宿主机 npm 不可用」，实际是 lockfile 问题 | **已修复**：删 `package-lock.json` 重装再生，`npm run build` 正常产出 dist（`index.html` + 38KB CSS + 345KB JS），`GET /` 已返回真实 React UI（非 static 占位）。再生 lockfile 已提交。后续直接 `npm install && npm run build` 即可 |
| **幂等缓存** | 编排器 `data/idempotency/` 默认 TTL 7 天，重复跑 demo 同一 `event_id` 会被判 duplicate | 跑前 `python scripts/demo_recovery.py` 或清 `data/` |
| **真实飞书凭证** | `FEISHU_APP_ID/SECRET`、`AILY_API_KEY` 均为占位符 | 真飞书实时联动需配置真凭证并切 `RUN_MODE=real`（B 计划前提） |

---

## 6. 整合现状与 B 计划（重要）

### 6.1 现状：两侧各自 Mock 跑通，实时跨侧未打通

契约（`openspec/specs/contracts/spec.md:56-57`「平台集成接口路径」）冻结了整合接口：

> 基址 `PLATFORM_API_BASE`（默认 `…/api`），路由 `POST /v1/candidates`、`POST /v1/card/callback`、`POST /v1/task/status`、`GET /v1/candidates/{candidate_id}`，鉴权 `Authorization: Bearer {PLATFORM_API_KEY}`。

**合规性对照**（B 计划已完成，平台已拉回契约合规）：

| 维度 | 契约要求 | 编排器（feishu-orchestrator） | 平台（labmemory-platform） |
|---|---|---|---|
| 鉴权头 | `Authorization: Bearer {key}` | ✅ `core/platform_client.py:284` | ✅ 双接受 Bearer + X-Platform-Api-Key（`app/api/deps.py`） |
| base 路径 | `{base}/v1/*`，base 含 `/api` | ✅ 默认 `…/api` | ✅ `/api/v1` 前缀（`app/api/meetings.py:39` + `app/api/integration.py`） |
| 路由覆盖 | 4 条（candidates/card/status/get） | ✅ 调全 4 条 | ✅ 4 条全实现 + 额外 `POST /api/v1/meetings` intake |
| 反向（平台→编排器） | `FeishuActionRequest` | ✅ webhook 接收 | ⚠️ 仍 `FEISHU_ORCHESTRATOR_MODE=mock`（真飞书凭证前提，非本次范围） |

**结论**：编排器与平台的**正向跨侧联动已打通并验证**（编排器 4 个出站调用模式直打真实平台，5/5 通过，见 §6.3）。反向（平台请求飞书建任务）仍为 mock，因其依赖真飞书凭证。

### 6.2 B 计划：平台契约合规化（已完成）

已通过 OpenSpec change `add-platform-intake-contract-compliance`（proposal + design + `platform-intake` spec + tasks，`validate` 通过后 `archive`）落地：

1. **鉴权**：`verify_platform_api_key` 双接受 `Authorization: Bearer` 与 `X-Platform-Api-Key`。
2. **base 路径**：`v1_router` 前缀 `/v1` → `/api/v1`。
3. **补路由**（新 `app/api/integration.py`）：`GET /api/v1/candidates/{id}`（扁平 + 富化 meeting_title/source_url）、`POST /api/v1/task/status`（candidate_id→Task，写 feishu_task_guid）、`POST /api/v1/card/callback`（嵌套信封解析 + action_type 分流 + **真实**六道闸门审计，不乐观 pass）。
4. **候选响应**：`receive_candidate` 补 `status:"submitted"` + `results[]` + `review_count`。
5. **Task 加列** `feishu_task_guid` + 轻迁移。
6. **夹具同步**：`scripts/e2e_test.py`、`scripts/mock_feishu_push.py` 改 `/api/v1/*` + Bearer。
7. **真跨侧 e2e**：新增 `scripts/cross_side_check.py`。

实现复用既有 helper（`_build_claim`、`_run_checks`）via lazy import（沿用 `meetings._chain_item` 既有跨模块模式），未做过度抽象。

### 6.3 跨侧实时 e2e 证据

`python -m scripts.cross_side_check` 以编排器同款 urllib + `Authorization: Bearer` 直打平台 4 条契约路由：

```
✓ health                       status=ok data_source=sqlite
✓ POST /api/v1/candidates      status=submitted created=True review_count=2
✓ GET /api/v1/candidates/{id}  candidate_id=cand_cross_001 meeting_title='跨侧联动验证会议' 扁平=True
✓ POST /api/v1/card/callback   status=blocked action_audit=needs_confirmation
                                  msg='需确认：审批门/资源门/失败边界门…'
✓ POST /api/v1/task/status     ok=True task_id=T_... feishu_task_guid=ftask_cross_demo_001
→ ✓ 全部通过 (5/5)
```

> card/callback 对 approve 诚实返回 `action_audit=needs_confirmation`（新建任务尚未审批/资源/失败边界就绪，六道闸门如实不放行）——这正是「行动前审计」产品价值，非乐观 pass。编排器侧 `card_handler` 仅在 `status=approved AND action_audit=pass` 后建飞书任务，平台如实返回确保不会越过审计建任务。

### 6.4 反向联动(平台 → 编排器)——已实现(备用通道)

> **新主路径不依赖本节**。v1.0.8 起飞书侧走"Aily 主动发卡",平台 webhook 反向通道作为**备用通道**保留。
>
> **2026-08-13 更新**：反向通路已落地（OpenSpec change `add-platform-feishu-reverse-linkage`）。
> - 编排器新增 `POST /webhook/platform`（`core/platform_action_handler.py` + `webhook_server.py`），按 `action_type` 分派到既有适配器，以 `idempotency_key` 幂等；mock 限 localhost、real 校验 `Authorization: Bearer {PLATFORM_API_KEY}`。
> - 平台新增 `app/services/feishu_client.py`，四个触发点（复核待办→`send_card`、任务启动→`create_task`、知识发布→`publish_doc`、审计阻断→`notify`）均为非阻断 fire-and-forget；`FEISHU_ORCHESTRATOR_MODE=mock` 时不真调。
> - 验证：`python -m scripts.reverse_linkage_check`（7/7，编排器 `RUN_MODE=mock` 即可，无需真飞书凭证）；平台 `pytest` 通过；编排器集成测试 38/38（原 `test_minutes_detail_uses_isolated_output_dir` 的 1 个既有 error 已由 change `fix-minutes-transcript-output-dir-consistency` 修复）。
> - 真飞书落地仍需真 `FEISHU_APP_ID/SECRET` + `RUN_MODE=real`（上线前人工验收）。

契约 `FeishuActionRequest`（平台 → 编排器，`send_card` / `create_task` / `update_base` / `publish_doc` / `notify`）描述了平台主动请求飞书侧执行动作的方向。**历史背景**（实现前勘查结论）：此方向曾两侧均未实现，且正向流程已覆盖建任务，故曾作为后续工作保留。

**新主路径下为何不依赖此通道**：
- **飞书侧由 Aily agent 接管**：Aily 通过 `lark-cli im --as bot` 主动发卡（最后一公里），避免 webhook 失败/重试/幂等管理的复杂度，且支持跨租户灵活路由（群聊/邮件降级）。
- **建任务场景已被正向流程覆盖**：新架构下任务创建由 Aily 调 `labmemory_create_review` 后在卡片回调链路完成，或由平台内部 task 状态机触发。
- **避免重复发卡**：若平台 webhook 与 Aily 发卡同时跑，会形成双发风险。

**真正实现反向联动需要**（B 级工作量 + 凭证门控）：
1. 编排器新增 `POST /webhook/platform` 端点，按 `FeishuActionRequest.action_type` 分派到既有 `im_card_adapter` / `task_adapter` / `docs_adapter` 等。
2. 平台新增 `app/services/feishu_client.py`，在特定业务节点（如「知识发布」→`publish_doc`、「复核待办」→`send_card`）组装并发送 `FeishuActionRequest` 到 `{FEISHU_ORCHESTRATOR_BASE_URL}/webhook/platform`。
3. 触发点设计（哪些平台状态变更应主动通知飞书侧）——需产品决策。
4. 走 OpenSpec change（新增端点 + 接口 = 系统行为变更）。
5. 真飞书侧落地仍需真 `FEISHU_APP_ID/SECRET` + `AILY_API_KEY` + `RUN_MODE=real`（mock 级可先验证通路）。

**建议**：新主路径下反向通道默认关闭（`FEISHU_ORCHESTRATOR_MODE=mock`），仅作为外部 BI / 监控系统的可选接入点保留。

---

## 7. 仓库结构（整合后）

```
.
├── README.md                          # 项目全貌
├── CLAUDE.md                          # 开发规范（OpenSpec 强制）
├── INTEGRATION.md                     # 本文件
├── openspec/                          # 共享规格源真相（两子系统共用）
│   ├── specs/                         # 16 个领域规格（含 contracts/）
│   └── changes/                       # 变更提案（含 archive/）
├── feishu-orchestrator/               # 飞书侧编排（韩广宁）
│   └── feishu-orchestrator/
│       ├── adapters/  core/  reliability/  contracts/  mock/  scripts/  tests/
└── labmemory-platform/                # 自研平台（林俊衡）
    ├── app/  (api/ contracts/ core/ db/ static/  main.py config.py schemas.py)
    ├── frontend/  (React 19 + Vite 6 + Tailwind 4)
    ├── scripts/  (seed_demo / e2e_test / mock_feishu_push / reset_demo)
    └── tests/
```

---

## 8. 交付清单

**A 计划（合并 + 各自可用）**
- [x] 两子系统并入 main（fast-forward，零冲突）
- [x] OpenSpec 源真相自洽（活跃 change 归零，`validate --all` 全绿）
- [x] 平台端到端可用：17 步决策全链路 + pytest 通过
- [x] 编排器可用：22 集成测试 + 11 体检通过
- [x] 三套契约 schema 两子系统语义一致
- [x] 本整合文档（架构/启动/Demo/验证/缺口）

**B 计划（跨侧联动合规化，已完成）**
- [x] OpenSpec change `add-platform-intake-contract-compliance`（proposal/design/spec/tasks）→ validate → archive
- [x] 平台鉴权双接受 Bearer + `/api/v1` 前缀 + 候选响应补 status
- [x] 3 条新契约路由（`app/api/integration.py`）+ Task 加 `feishu_task_guid`
- [x] 平台夹具同步 `/api/v1` + Bearer
- [x] 真跨侧 e2e `scripts/cross_side_check.py` → 5/5 通过
- [x] §6 合规对照表正向全 ✅ + §6.3 跨侧 e2e 证据

**后续待办**
- [x] **仓库运行时产物清理**：解除 6 个 `data/`/`logs` 文件的 git 跟踪（commit `1331e53`，`.gitignore` 已覆盖）
- [x] **平台→编排器反向联动**：备用通道已实现（`/webhook/platform` + `feishu_client.py` + 四触发点 + `reverse_linkage_check` 7/7），新主路径不依赖，详见 §6.4
- [x] **前端 React UI 构建**：根因是提交的 `package-lock.json` 损坏（非宿主机 npm），已删 lockfile 重装再生 + `npm run build` 产出 dist；`GET /` 返回真实 React UI。再生 lockfile 已提交（产物 `frontend/dist/` 已 gitignore）
- [ ] **`candidate_id` 索引列**：demo 规模 JSON 扫描够用，生产规模另起 change
