# LabMemory Platform

LabMemory 自研可信决策与实验记忆平台。接收 [`feishu-orchestrator`](../feishu-orchestrator) 推送的飞书会议数据，完成「会后复核 -> 主张/参数版本 -> 行动前审计 -> 任务执行 -> 结果回流 -> 知发布」全链路，并以实验护照统一回看。

## 核心规则

1. **三角色均能操作** 会后复核、行动审计、结果回流、查看实验护照：项目负责人（PI）、实验负责人（Lead）、执行人（Executor）。
2. **会后复核** 不存在「打回修改」中间态：直接确认 / 修改后确认 / 直接结束（不进入数据链路）。状态机仅 `pending` / `processed`。确认后生成主张（含当前参数版本）。
3. **行动审计** 通过后，PI / Lead / Executor 均可启动任务；引用旧版本主张时自动阻断，可一键修正为当前版本。
4. **结果回流** 三角色均可提交结果；**每个任务仅可提交一次**，提交后任务自动标记为 `completed`，无需单独「标记完成」；**仅 PI / Lead 可发布为知识**（更新主张 `knowledge_status`，可附带失败边界卡与模型偏差卡）。
5. **实验管理（创建实验/项目/成员）仅 PI 可操作**；**实验护照列表**三角色均可查看（PI/Admin 看全部，其他角色看自己参与的实验）。
6. **唯一跟踪**：`experiment_id` 跨会议统一跟踪实验；`meeting_id` 跟踪单次会议操作。一个项目多个实验，一个实验多个任务，**一个会议最终形成一个任务**。
7. **参数不硬编码**：主张/任务/结果的参数 JSON 完全由会议候选 + 复核修改决定。前端提供结构化表格编辑器（ParameterEditor），支持「高级 JSON」开关应对复杂结构。
8. **实验护照**：
   - 列表页：以卡片展示所有可见实验，含会议数/待复核/任务/已发布知识统计，点击进入详情。
   - 详情页：数据关系链按 **会议 ID** 组织（一个实验多个会议，每次会议展开 复核->主张->任务->审计->结果 流向）；统一时间线按 **实验 ID** 组织（按时间倒序展示所有审计事件）。
   - 结果回流完成 = 会议任务结束。
9. **统一弹窗**：全站使用 DialogHost 组件替代原生 `alert/confirm`，支持 info/success/warning/error 四种语义 + danger 确认按钮。

## 状态机

| 对象 | 状态 |
|---|---|
| 会后复核 | `pending` -> `processed`（`decision=confirmed` 或 `ended`） |
| 主张 | `current` -> `superseded`（新主张替代旧主张）；`knowledge_status` 独立：`null`/`supported`/`partially_supported`/`refuted` |
| 任务 | `draft` -> `audited` -> `running` -> `completed`（提交结果即完成）；`blocked` 表示审计未通过 |
| 行动审计 | `pending` -> `passed` / `blocked` |
| 结果 | `submitted` -> `published`；`frozen` 表示版本不匹配。**每个任务仅一条结果** |

## 目录结构

```
labmemory-platform/
├── app/
│   ├── main.py              # FastAPI 入口 + 静态前端
│   ├── config.py            # pydantic-settings 单一来源
│   ├── schemas.py           # Pydantic 请求/响应模型
│   ├── core/
│   │   ├── errors.py        # 领域异常
│   │   └── security.py      # 密码哈希 + JWT
│   ├── db/
│   │   ├── base.py          # SQLAlchemy Base + Mixins
│   │   ├── session.py       # 引擎（SQLite 默认，可切 PostgreSQL）
│   │   └── models.py        # 全部领域模型（单文件）
│   └── api/
│       ├── deps.py          # 依赖：DB / 当前用户 / 角色校验
│       ├── auth.py          # 登录 / 当前用户
│       ├── admin.py         # 演示数据重置（前端按钮后端）
│       ├── experiments.py   # 实验管理（仅 PI）
│       ├── meetings.py      # /v1/meetings + /v1/candidates + 复核
│       ├── tasks.py         # 行动审计 + 任务启动 + 一键修正
│       ├── results.py       # 结果提交（防重复 + 自动完成） + 知识发布
│       ├── passport.py      # 实验护照列表 + 详情
│       ├── control_tower.py # 研发控制塔聚合指标
│       ├── brief.py         # 会前研讨包
│       └── qa.py            # 可信知识问答（关键词检索 + 拒答）
├── frontend/                # React 19 + Vite 6 + Tailwind 4
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx          # 路由 + 鉴权守卫 + DialogHost 挂载
│   │   ├── api.ts           # fetch 封装
│   │   ├── store.ts         # Zustand 鉴权状态
│   │   ├── dialog.ts        # 全局 Dialog 状态 + dialog.alert/confirm API
│   │   ├── types.ts         # 与后端 schema 对齐
│   │   ├── index.css        # Tailwind 4 + 原型视觉变量
│   │   ├── components/
│   │   │   ├── Layout.tsx
│   │   │   ├── DialogHost.tsx       # 统一弹窗渲染
│   │   │   ├── ParameterEditor.tsx  # 结构化参数表格编辑器
│   │   │   └── RequireRole.tsx
│   │   └── pages/           # 15 个页面
│   ├── package.json
│   └── vite.config.ts
├── scripts/
│   ├── seed_demo.py         # 初始化演示账号 + 项目 + 实验 + 完整端到端场景
│   ├── mock_feishu_push.py  # 模拟飞书编排器推送会议+候选（走 /v1 API）
│   ├── reset_demo.py        # 清空业务数据 + 重新注入（API/直写库两种模式）
│   └── e2e_test.py          # E2E 全链路（14 步）
├── tests/
│   ├── conftest.py          # 测试环境变量
│   └── test_e2e.py          # pytest 包装
├── data/labmemory.db        # SQLite 文件库（gitignore）
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

## 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | ≥ 3.12 | 后端运行时（FastAPI + SQLAlchemy + Pydantic v2） |
| Node.js | ≥ 20.19 | 前端构建（Vite 6 / React 19 / Tailwind 4） |
| npm | ≥ 10 | 随 Node.js 安装 |
| conda | 可选 | 推荐；也可用 `venv` 代替 |

建议创建专用 conda 环境：

```bash
conda create -n labmemory python=3.12 -y
```

> 使用 venv 替代 conda 时，将下文所有 `conda run -n labmemory <cmd>` 替换为在已激活的虚拟环境中直接执行 `<cmd>`。

## 启动方式

> **推荐路径（演示/生产）**：安装依赖 → 初始化演示数据 → 构建前端 → 启动后端（前端由后端统一挂载）。
> **开发路径**：安装依赖 → 启动后端 → `npm run dev`（Vite 热更新 + `/api` 代理）。

### 0. 配置环境变量（可选）

`app/config.py` 通过 pydantic-settings 读取项目根目录的 `.env` 文件；**不创建 `.env` 也能用默认值直接启动**。需要自定义端口、密钥或切换数据库时再复制：

```bash
cp .env.example .env
```

### 1. 安装依赖

```bash
# 后端（conda 环境 `labmemory`；[dev] 附带 pytest，供端到端测试用）
conda run -n labmemory pip install -e ".[dev]"

# 或使用 requirements.txt（已含 dev 依赖）
# conda run -n labmemory pip install -r requirements.txt

# 确保 SQLite 数据目录存在（DATABASE_URL 为相对路径 sqlite:///./data/labmemory.db）
mkdir -p data

# 前端
cd frontend && npm install && cd ..
```

> 首次进入全新的 `data/` 时数据库文件会在启动时自动创建，但**目录本身不会**，请务必先执行 `mkdir -p data`，否则 SQLite 会报 `unable to open database file`。

### 2. 初始化演示数据

```bash
conda run -n labmemory python -m scripts.seed_demo
```

幂等：重复运行不会重复创建或覆盖数据。创建 4 个账号（密码均为 `123456`）：

| 用户名 | 角色 | 说明 |
|---|---|---|
| `pi` | PI | 项目负责人，可管理实验、发布知识 |
| `lead` | Lead | 实验负责人，可发布知识 |
| `executor` | Executor | 执行人，可走完复核/审计/回流链路 |
| `admin` | Admin | 管理员，全部权限 |

演示项目 `PROJ-DEMO-001`；演示实验 `EXP-DEMO-001`；预置 4 类场景：
- `meet_seed_completed`：已完成实验链（65℃ 部分支持，含失败边界卡）
- `meet_seed_80c` -> `meet_seed_70c`：80℃ 任务被 70℃ 主张阻断（演示旧版本拦截）
- `meet_seed_pending`：待复核会议（0.8 eq 复验）

> 也可以跳过本步，改用「研发控制塔」页面的"重置为完整链路"按钮注入演示数据（见下文使用方式）。

### 3. 构建前端

```bash
cd frontend && npm run build && cd ..
```

构建产物输出到 `frontend/dist/`，由后端 `main.py` 自动挂载到根路径（存在 `dist/index.html` 时生效，否则回退到占位页并打印提示）。

### 4. 启动服务

```bash
conda run -n labmemory uvicorn app.main:app --port 8081 --reload
```

启动后验证：

```bash
curl http://127.0.0.1:8081/health
# {"status":"ok","service":"labmemory-platform","version":"2.0.0","data_source":"sqlite",...}
```

打开 http://127.0.0.1:8081 即可登录（`pi` / `123456`）。OpenAPI 文档位于 http://127.0.0.1:8081/docs。

> `--reload` 仅用于开发；若以 `nohup`/后台方式启动，请去掉 `--reload` 并把日志重定向到文件。

### 5. 前端开发模式（可选，热更新）

后端先按第 4 步启动在 `8081`，另开一个终端：

```bash
cd frontend && npm run dev
```

- 访问 http://localhost:5174（Vite dev server）
- `vite.config.ts` 已配置将 `/api`、`/v1`、`/health` 代理到 `http://localhost:8081`，前端请求与后端同源，无需额外 CORS 配置
- 修改 `frontend/src/` 代码即时热更新，无需重新 build
- 演示/生产请用第 3 + 4 步的 build 模式

### 6. 端到端测试

```bash
# 方式 A：pytest（in-memory SQLite，自动隔离，无需启动服务）
conda run -n labmemory pytest tests/test_e2e.py -q

# 方式 B：真实 HTTP 服务 + 模拟飞书数据
conda run -n labmemory uvicorn app.main:app --port 8081 &
conda run -n labmemory python -m scripts.e2e_test
```

E2E 步骤覆盖：登录 -> 飞书推 MeetingPackage + CandidatePackage -> 修改后确认（生成主张+任务） -> 行动审计 -> 任务启动 -> 结果提交（任务自动完成） -> PI 发布知识（更新 `knowledge_status=partially_supported`） -> 护照验证 -> 权限校验（执行人不能发布、不能访问实验管理） -> 第二次会议验证旧主张被 supersede。

## 使用方式

### 飞书 UUAP 免登登录（默认开启）

平台支持通过飞书统一账号认证（UUAP，即飞书开放平台「网页应用」OAuth 2.0）直接登录：

- **新用户自动注册**：飞书用户首次登录即自动注册为平台账号，默认最低权限角色
  `viewer`（只读访客）——未分配实验成员时不可见任何实验数据。
- **管理员可控可见范围**：管理员在「用户与权限」（`/admin/users`）调整每位用户的
  全局角色（viewer/executor/lead/pi/admin），并通过**实验成员**精确控制其能看到的实验范围。
- **两种模式**：
  - `FEISHU_OAUTH_MODE=mock`（默认）：无需真实飞书凭据，登录页显示「模拟飞书登录」
    表单，输入任意工号即可验证自动注册流程。
  - `FEISHU_OAUTH_MODE=real`：在飞书开放平台创建自建应用，配置
    `FEISHU_OAUTH_APP_ID` / `FEISHU_OAUTH_APP_SECRET`，并在「安全设置-重定向 URL」
    登记 `FEISHU_OAUTH_REDIRECT_URI`。登录页跳转飞书授权 → 回调自动登录/注册。
- 密码登录默认保留作为管理员/演示兜底（`PASSWORD_LOGIN_ENABLED=false` 可关闭）。

### 模拟飞书数据的三种方式

#### 方式一：前端按钮（推荐演示用）

登录后进入「研发控制塔」页面，底部"快速开始 Demo"卡片有三个按钮：

| 按钮 | 效果 |
|---|---|
| **重置为待复核** | 清空业务数据，推送 4 条待复核会议（65℃/80℃/70℃/催化剂0.8eq），需手动走完链路 |
| **重置为完整链路** | 清空后注入完整端到端场景（65℃已发布+失败边界卡、80℃被阻断、70℃current主张、1条待复核） |
| **清空** | 只清业务数据，不注入 |

后端走 `POST /api/admin/reset-demo?mode=clear|pending|full`，前端用 Dialog 弹窗二次确认。

#### 方式二：CLI 脚本（灵活定制）

先启动后端（见上文第 4 步），然后：

```bash
# 推送单条简单会议（快速验证）
conda run -n labmemory python -m scripts.mock_feishu_push single

# 推送完整演示场景（4 个会议，覆盖不同链路状态）
conda run -n labmemory python -m scripts.mock_feishu_push demo

# 重置 + 重新注入
conda run -n labmemory python -m scripts.reset_demo              # 走 /v1 API（待复核状态）
conda run -n labmemory python -m scripts.reset_demo --db-only    # 直接写库（完整链路，不需后端运行）
conda run -n labmemory python -m scripts.reset_demo --clear-only # 仅清空

# 自定义后端地址/API Key
conda run -n labmemory python -m scripts.mock_feishu_push demo \
  --base-url http://localhost:8081 \
  --api-key dev-platform-api-key-please-rotate
```

#### 方式三：手动构造 HTTP 请求

飞书集成契约见 `app/contracts/*.schema.json`。核心是两个接口（Header: `x-platform-api-key`）：

**1. 推送会议包** `POST /v1/meetings`

```json
{
  "schema_version": "1.0.0",
  "source": "feishu_minutes",
  "source_object_id": "minutes_xxx",
  "meeting_id": "meet_001",
  "title": "温度调整评审",
  "captured_at": "2026-08-10T10:00:00Z",
  "organizer": "陈博士",
  "participants": ["陈博士", "王工程师"],
  "content": {
    "transcript": [
      {"speaker": "陈博士", "text": "建议温度调到75度", "start_offset_sec": 10}
    ],
    "summary": "温度调整评审"
  },
  "metadata": {
    "experiment_id": "EXP-DEMO-001",
    "project_id": "PROJ-DEMO-001"
  }
}
```

**2. 推送候选包** `POST /v1/candidates`（`source_package_id` 必须等于上面 `meeting_id`）

```json
{
  "schema_version": "1.0.0",
  "source_package_id": "meet_001",
  "aily_skill_version": "aily-labmemory-v1.0",
  "candidates": [{
    "candidate_id": "CDR-001",
    "type": "parameter_change",
    "title": "温度 70->75℃",
    "experiment_ref": "EXP-DEMO-001",
    "parameters": [{"name": "temperature", "value": "75", "unit": "℃"}],
    "confidence": 0.85,
    "evidence": [{"speaker": "陈博士", "text": "建议温度调到75度", "start_offset_sec": 10}],
    "status": "pending_review",
    "needs_review": true
  }]
}
```

**关键约束**：
- `metadata.experiment_id` 必填，且实验必须已由 PI 创建
- `source_package_id` 必须等于已推送的 `meeting_id`
- 同一 `meeting_id` 重复推送是幂等的（返回 `created: false`）
- 推送的会议默认进入「待复核」状态，需在前端确认后才生成主张和任务

### 端到端测试路径

推荐用「重置为完整链路」按钮注入数据后，按以下路径验证：

1. **会后复核**（`/review`）：进入待复核会议 -> 修改参数（结构化表格）-> 确认生成主张+任务草稿
2. **行动审计**（`/audit`）：对 80℃ 任务运行审计 -> 触发版本阻断（70℃ 已是 current）-> 一键修正生成新任务
3. **任务执行**（`/audit/:taskId`）：审计通过后启动任务
4. **结果回流**（`/result/:taskId`）：提交实际参数+指标 -> 任务自动完成 -> PI/Lead 发布为知识（含失败边界卡）
5. **实验护照**（`/passport`）：列表查看所有实验统计 -> 点击进入详情 -> 查看数据关系链 + 统一时间线
6. **可信问答**（`/qa`）：基于已发布知识提问，验证引用与拒答

## 前端页面

| 路由 | 页面 | 说明 |
|---|---|---|
| `/login` | 登录 | 飞书 UUAP / 模拟登录 / 密码兜底 |
| `/admin/users` | 用户与权限（Admin） | UUAP 用户角色与可见实验范围管理 |
| `/tower` | 研发控制塔 | KPI 指标 + 端到端闭环 + 需要处理项 + 演示数据重置按钮 |
| `/review` | 会后复核列表 | 待处理/已处理/全部 三 tab，统计精确到当前显示数/总数 |
| `/review/:meetingId` | 会后复核台 | 三值留痕 + 6 道闸门 + 结构化参数编辑 + 确认/结束 |
| `/compiler/:meetingId` | 决策编译器 | 逐字稿 + AI 候选对象 + 快速确认 |
| `/audit` | 行动审计列表 | 全部/待审计/已阻断/已通过 四 tab |
| `/audit/:taskId` | 行动前审计 | 5 项检查 + 版本对比 + 一键修正 |
| `/result` | 结果回流列表 | 待提交/待发布/已发布/全部 四 tab |
| `/result/:taskId` | 结果与模型回流 | 计划vs实际 + 提交即完成 + 失败边界卡 + 模型偏差卡 |
| `/experiments` | 实验管理（PI） | 创建实验/项目/成员 |
| `/brief/:experimentId` | 会前研讨包 | 当前主张 + 上一轮结果 + 失败边界 |
| `/passport` | 实验护照列表 | 卡片网格，统计会议/待复核/任务/已发布知识 |
| `/passport/:experimentId` | 实验护照详情 | 数据关系链（按会议）+ 统一时间线（按实验） |
| `/qa` | 可信知识问答 | 关键词检索 + 拒答 + 引用 |
| `/team` | 团队与落地 | 静态团队信息 |

## 飞书侧接入

`feishu-orchestrator` 通过以下接口推送数据（请求头 `x-platform-api-key`）：

| 接口 | 用途 |
|---|---|
| `POST /v1/meetings` | 接收 MeetingPackage（`metadata.experiment_id` 必填） |
| `POST /v1/candidates` | 接收 CandidatePackage（`source_package_id` = meeting_id） |

接口契约见 `app/contracts/*.schema.json`，与 `feishu-orchestrator` 共享。

> **反向联动（平台 → 编排器）**：平台在「复核待办 / 任务启动 / 知识发布 / 审计阻断」四个节点通过 `app/services/feishu_client.py` 向编排器 `POST /webhook/platform` 下发 `FeishuActionRequest`（`send_card` / `create_task` / `publish_doc` / `notify`）。默认 `FEISHU_ORCHESTRATOR_MODE=mock` 不真调；设为 `real` 并配置 `FEISHU_ORCHESTRATOR_BASE_URL` 后真调（编排器 `RUN_MODE=mock` 即可端到端验证，无需真飞书凭证）。验证脚本：`python -m scripts.reverse_linkage_check`。

## 关键 API

### 平台前端 API

| 接口 | 角色 | 用途 |
|---|---|---|
| `POST /api/auth/login` | 公开 | 密码登录获取 JWT（受 PASSWORD_LOGIN_ENABLED 控制） |
| `GET /api/auth/feishu/authorize` | 公开 | 登录页初始化（返回登录方式 / 授权 URL） |
| `GET /api/auth/feishu/callback` | 公开 | 飞书授权回调（换 token + 自动注册 + 跳转前端） |
| `POST /api/auth/feishu/mock-login` | 公开(mock) | 模拟飞书免登（本地验证自动注册） |
| `GET /api/admin/users` | Admin | 用户列表（角色 / 来源 / 可见实验） |
| `PATCH /api/admin/users/{id}` | Admin | 调整用户全局角色 |
| `POST /api/admin/users/{id}/members` | Admin | 添加实验成员（扩大可见范围） |
| `DELETE /api/admin/users/{id}/members/{exp}` | Admin | 移除实验成员（收回可见范围） |
| `GET /api/auth/me` | 三角色 | 当前用户信息 |
| `GET /api/control-tower` | 三角色 | 控制塔聚合指标 |
| `POST /api/admin/reset-demo?mode=` | PI/Admin | 演示数据重置（clear/pending/full） |
| `POST /api/projects` | PI | 创建项目 |
| `GET /api/projects` | PI | 列出项目 |
| `POST /api/experiments` | PI | 创建实验 |
| `GET /api/experiments` | PI | 列出实验 |
| `POST /api/experiments/{id}/members` | PI | 添加成员 |
| `GET /api/experiments/{id}/brief` | 三角色 | 会前研讨包 |
| `GET /api/meetings` | 三角色 | 列出会议（含 chain item） |
| `GET /api/meetings/{meeting_id}` | 三角色 | 会议详情（含逐字稿+候选） |
| `POST /api/meetings/{meeting_id}/review` | 三角色 | 确认 / 修改后确认 / 结束 |
| `POST /api/tasks/{task_id}/audit` | 三角色 | 行动前审计 |
| `GET /api/tasks/{task_id}/audit/compare` | 三角色 | 旧版本对比（阻断展示） |
| `POST /api/tasks/{task_id}/audit/fix` | 三角色 | 一键修正为当前版本 |
| `POST /api/tasks/{task_id}/start` | 三角色 | 启动任务（审计通过后） |
| `POST /api/tasks/{task_id}/results` | 三角色 | 提交结果（防重复，提交即完成） |
| `POST /api/results/{result_id}/publish` | PI/Lead | 发布为知识（可附失败边界/模型偏差） |
| `GET /api/passports` | 三角色 | 实验护照列表（按可见性过滤） |
| `GET /api/experiments/{id}/passport` | 三角色 | 实验护照详情 |
| `POST /api/qa/ask` | 三角色 | 可信知识问答 |

### 飞书集成 API（`/v1/*`，需 `x-platform-api-key`）

| 接口 | 用途 |
|---|---|
| `POST /v1/meetings` | 接收 MeetingPackage |
| `POST /v1/candidates` | 接收 CandidatePackage |

## 配置

通过环境变量或 `.env` 文件配置（见 `.env.example`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/labmemory.db` | SQLite 默认；可切 `postgresql://...` |
| `PLATFORM_API_KEY` | `dev-platform-api-key-please-rotate` | 飞书编排器调用 `/v1/*` 的鉴权 |
| `JWT_SECRET` | `dev-jwt-secret-please-rotate` | 平台用户 JWT 签名 |
| `JWT_ALGORITHM` | `HS256` | JWT 签名算法 |
| `JWT_EXPIRE_HOURS` | `24` | JWT 有效期 |
| `SERVER_HOST` | `0.0.0.0` | 服务监听地址 |
| `SERVER_PORT` | `8081` | 服务端口 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `CORS_ORIGINS` | `*` | CORS 白名单 |
| `FEISHU_ORCHESTRATOR_BASE_URL` | `http://localhost:8080` | 飞书编排器地址 |
| `FEISHU_ORCHESTRATOR_MODE` | `mock` | 飞书编排器模式（mock/real） |
| `FEISHU_OAUTH_MODE` | `mock` | 飞书免登模式（mock/real） |
| `FEISHU_OAUTH_APP_ID` | 空 | 飞书自建应用 App ID |
| `FEISHU_OAUTH_APP_SECRET` | 空 | 飞书自建应用 App Secret |
| `FEISHU_OAUTH_REDIRECT_URI` | `http://localhost:8081/api/auth/feishu/callback` | 授权回调（需在飞书开放平台登记） |
| `UUAP_AUTO_REGISTER_ROLE` | `viewer` | 新用户自动注册默认角色（最低权限） |
| `PASSWORD_LOGIN_ENABLED` | `true` | 是否保留密码登录 |

> **注意**：`DATABASE_URL` 是相对路径 `sqlite:///./data/labmemory.db`，必须从项目根目录启动后端，否则会找不到数据库文件。

## 开发约定

- 本项目遵循 OpenSpec 规范驱动开发（见根目录 `CLAUDE.md`），任何影响系统行为的变更须先创建 change 提案。
- 前端只允许在 `labmemory-platform/` 内修改，不可改动文件夹之外的文件。
- 参数编辑统一使用 `ParameterEditor` 组件（结构化表格 + 高级 JSON 开关），不直接操作 JSON 文本。
- 全站弹窗使用 `dialog.alert()` / `dialog.confirm()`，不使用原生 `alert()` / `confirm()`。
