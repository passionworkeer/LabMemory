# LabMemory 整合交付文档（INTEGRATION）

> 本文件是飞书编排子系统（`feishu-orchestrator`）与自研平台子系统（`labmemory-platform`）合并到同一仓库后的**整合运维与技术说明**，面向团队与评委。
> 项目全貌见 [`README.md`](./README.md)；开发规范见 [`CLAUDE.md`](./CLAUDE.md)；接口契约见 [`openspec/specs/contracts/spec.md`](./openspec/specs/contracts/spec.md)。

---

## 0. 一句话现状

两个子系统已并入同一仓库、**两侧各自端到端跑通**（平台 17 步决策全链路 + pytest、编排器 22 个集成测试 + 11 项体检，全部绿）；**实时跨侧联动尚未实现**——二者目前各对着对方的 Mock 运行（契约设计的"并行开发"阶段产物），把两侧真正打通是 B 计划（见第 6 节）。

---

## 1. 架构总览

```
飞书会议/妙记
     │
     ▼
┌──────────────────────────────┐
│  feishu-orchestrator (8080)  │   飞书侧编排与 AI 接入
│  · 妙记/事件接入              │   负责人：韩广宁
│  · Aily Skill 编译            │
│  · 卡片/任务/多维表格/知识库   │
│  · 幂等 + 重试 + 验签         │
└──────────────┬───────────────┘
               │  CandidatePackage (POST /v1/candidates)
               │  CardCallback      (POST /v1/card/callback)
               │  TaskStatus        (POST /v1/task/status)
               │  —— 契约：openspec/specs/contracts/spec.md
               ▼
┌──────────────────────────────┐
│  labmemory-platform (8081)   │   自研可信决策平台
│  FastAPI + React + SQLite    │   负责人：林俊衡
│  · 会后复核 → 主张/版本      │
│  · 行动前审计（六道闸门）     │
│  · 任务执行 + 结果回流        │
│  · 知识发布 + 实验护照        │
│  · 决策问答 / 会前研讨包      │
└──────────────────────────────┘
```

**数据流向**：妙记 → 编排器组装 `MeetingPackage` → Aily 编译为 `CandidatePackage` → 提交平台 → 平台走「复核 → 主张版本 → 行动审计 → 任务 → 结果 → 知识发布 → 护照」全链路。反向：平台决策通过后通过 `FeishuActionRequest` 请求编排器发卡片/建任务。

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
| 端口 | 平台 8081、编排器 8080 | 空闲 ✅ |

### 2.2 装依赖

```bash
# 平台后端
pip install -r labmemory-platform/requirements.txt

# 前端（标准 npm 环境；本机 npm 环境 bug 见 §5）
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
| `PLATFORM_API_KEY` | `dev-platform-api-key-please-rotate` | 编排器调用 `/v1/*` 的鉴权 key |
| `JWT_SECRET` | `dev-jwt-secret-please-rotate` | 平台用户 JWT 签名 |
| `FEISHU_ORCHESTRATOR_MODE` | `mock` | 平台→编排器方向：`mock` 不真调飞书侧 |

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

### 2.5 编排器（默认 Mock 模式，无需真飞书凭证）

```bash
cd feishu-orchestrator/feishu-orchestrator
python scripts/run_pipeline.py --demo     # 端到端 demo（妙记→Aily→提交平台→发卡片）
python scripts/health_check.py            # 11 项模块体检
python -m core.webhook_server            # 起 webhook 服务（/webhook/event, /webhook/card, /health）
```

> 真实飞书联动需在 `config/env.example` 配置真 `FEISHU_APP_ID/SECRET`、`AILY_API_KEY`、`PLATFORM_API_BASE` 并切 `RUN_MODE=real`。当前为占位符，故用 Mock。

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
| **前端构建（本机）** | 本机 `npm install` 触发 npm 内部错误 `Exit handler never called!`，导致 `node_modules/.bin/tsc\|vite` 软链未生成，`npm run build` 报 `tsc 不是命令`；多次 `npm ci`/清缓存/换 ASCII 路径均复现 | **本机 npm 环境问题，非项目缺陷**——前端源码（标准 Vite 6 + React 19 + Tailwind 4）在正常 npm 环境可正常 `npm install && npm run build`。当前平台回退服务 `app/static/index.html` 登录占位，API/Swagger/全链路均不受影响。修复建议：换一台 npm 正常的机器构建，或重装 Node.js / 升级 npm / 关闭 AV 后重试 |
| **幂等缓存** | 编排器 `data/idempotency/` 默认 TTL 7 天，重复跑 demo 同一 `event_id` 会被判 duplicate | 跑前 `python scripts/demo_recovery.py` 或清 `data/` |
| **真实飞书凭证** | `FEISHU_APP_ID/SECRET`、`AILY_API_KEY` 均为占位符 | 真飞书实时联动需配置真凭证并切 `RUN_MODE=real`（B 计划前提） |

---

## 6. 整合现状与 B 计划（重要）

### 6.1 现状：两侧各自 Mock 跑通，实时跨侧未打通

契约（`openspec/specs/contracts/spec.md:56-57`「平台集成接口路径」）冻结了整合接口：

> 基址 `PLATFORM_API_BASE`（默认 `…/api`），路由 `POST /v1/candidates`、`POST /v1/card/callback`、`POST /v1/task/status`、`GET /v1/candidates/{candidate_id}`，鉴权 `Authorization: Bearer {PLATFORM_API_KEY}`。

**合规性对照**：

| 维度 | 契约要求 | 编排器（feishu-orchestrator） | 平台（labmemory-platform） |
|---|---|---|---|
| 鉴权头 | `Authorization: Bearer {key}` | ✅ `core/platform_client.py:284` | ❌ 校验 `X-Platform-Api-Key`（`app/api/deps.py:77`） |
| base 路径 | `{base}/v1/*`，base 含 `/api` | ✅ 默认 `…/api` | ❌ `/v1` 挂根（`app/api/meetings.py:39`），无 `/api` |
| 路由覆盖 | 4 条（candidates/card/status/get） | ✅ 调全 4 条 | ❌ 仅 `POST /v1/candidates`；缺 card/status/get；多一契约没有的 `POST /v1/meetings` |
| 反向（平台→编排器） | `FeishuActionRequest` | ✅ webhook 接收 | ❌ `FEISHU_ORCHESTRATOR_MODE=mock`，不真调 |

**结论**：编排器**完全合规**；平台**偏离契约 5 处**。两侧各自的测试（平台 `e2e_test`/`mock_feishu_push`、编排器 `test_integration`）都用各自的（平台是偏离的）私有接口，所以内部自洽、能跑通，但**把真实编排器指向真实平台会全部 403/404**。

### 6.2 B 计划：把平台拉回契约合规（本次不做，路线图）

按 `CLAUDE.md` 第 0 节，改接口属系统行为变更，**必须走 OpenSpec change**。草案要点：

1. **鉴权**：`app/api/deps.py:77` `verify_platform_api_key` 改为接受 `Authorization: Bearer {PLATFORM_API_KEY}`（或双接受，过渡期兼容）。
2. **base 路径**：`/v1` 路由挂到 `/api` 前缀下；或统一文档约定 `PLATFORM_API_BASE` 不含 `/api`（二选一，前者更省配置）。
3. **补路由**：`POST /v1/card/callback`（卡片回调入审核）、`POST /v1/task/status`（任务状态回写）、`GET /v1/candidates/{candidate_id}`（候选详情）。同步评估是否保留契约外的 `POST /v1/meetings`（平台 e2e 依赖它，或迁出到独立 intake）。
4. **同步测试夹具**：`scripts/e2e_test.py`、`scripts/mock_feishu_push.py` 改用契约接口（Bearer + 4 路由）。
5. **OpenSpec change**：新增平台侧 integration spec 领域（建议 `platform-intake`），含 proposal + ADDED specs + tasks，`openspec validate` 通过后 `archive`。
6. **真 e2e**：编排器 `RUN_MODE=real`、`PLATFORM_API_BASE=http://localhost:8081/api` 指向本地平台，跑通「候选提交 → 卡片回调 → 任务状态回写」闭环（前提：真 FEISHU 凭证，否则仍止于 mock_feishu_push 模拟）。

> B 计划完成后，本文件 §6.1 的合规对照表应全部 ✅，并新增一节"跨侧实时 e2e"。

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

## 8. 交付清单（A 计划）

- [x] 两子系统并入 main（fast-forward，零冲突）
- [x] OpenSpec 源真相自洽（16 领域规格，活跃 change 归零，`validate --all` 全绿）
- [x] 平台端到端可用：17 步决策全链路 + pytest 通过
- [x] 编排器可用：22 集成测试 + 11 体检通过
- [x] 三套契约 schema 两子系统语义一致
- [x] 本整合文档（架构/启动/Demo/验证/缺口/B 计划）
- [ ] **B 计划**：平台契约合规化 + 跨侧实时 e2e（见 §6.2）
