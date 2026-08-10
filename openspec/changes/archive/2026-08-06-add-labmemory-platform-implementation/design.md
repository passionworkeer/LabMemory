# Design: LabMemory Platform Implementation

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  浏览器 (index.html + app.js)                            │
└────────────────────────┬────────────────────────────────┘
                         │ JWT (Bearer)
┌────────────────────────▼────────────────────────────────┐
│  FastAPI (app/main.py)                                   │
│  ├── /v1/* (契约端点, Bearer PLATFORM_API_KEY)           │
│  ├── /web/* (前端端点, JWT)                              │
│  ├── /static/* + / (HTML/JS)                             │
│  └── /health, /docs                                     │
├─────────────────────────────────────────────────────────┤
│  Services Layer                                          │
│  ├── candidate_ingest.py  (幂等接收 CandidatePackage)    │
│  ├── review.py            (三值留痕, 语义分类)            │
│  ├── gates.py             (六道质量闸门)                  │
│  ├── version.py           (参数版本状态机, 单 active)     │
│  ├── audit.py             (5 检查 + 3 态结论 + 一键修正)  │
│  ├── task.py              (任务生命周期 + TaskRevision)   │
│  ├── result.py            (回流 + 冻结 + 失败卡)          │
│  ├── passport.py          (跨对象时间线聚合)              │
│  ├── permissions.py       (5 角色 + 项目成员)             │
│  └── qa.py                (可信问答 + 拒答)               │
├─────────────────────────────────────────────────────────┤
│  Core                                                    │
│  ├── state_machine.py     (通用状态机 + 合法迁移表)       │
│  ├── audit_log.py         (write_audit_event 通用助手)   │
│  ├── idempotency.py       (@idempotent 装饰器)           │
│  └── errors.py            (DomainError 层级)             │
├─────────────────────────────────────────────────────────┤
│  Adapters                                                │
│  ├── feishu_client.py     (Mock + Real + factory)        │
│  └── contract_validator.py (jsonschema 校验)             │
├─────────────────────────────────────────────────────────┤
│  SQLAlchemy 2.0 ORM (22 models)                          │
│  └── Alembic migrations                                  │
└────────────────────────┬────────────────────────────────┘
                         │
                ┌────────▼────────┐
                │  PostgreSQL 16  │
                └─────────────────┘
```

## Key Decisions

### 1. 共享 Base + 统一 import 路径
所有模型继承 `app/db/base.py::Base`。所有 import 用 `from app.db.models.X import Y` 绝对路径。修复脚手架每文件独立 Base 导致 relationship 失效的问题。

### 2. 纯 PostgreSQL（用户确认）
Docker Compose 起 `postgres:16-alpine`。测试连独立 `labmemory_test` 库，每测试事务回滚隔离。不引入 SQLite。

### 3. 双层鉴权
- 契约端点（`/v1/*`）：`Authorization: Bearer {PLATFORM_API_KEY}`（env 常量），匹配 `openspec/specs/contracts/spec.md`。
- 前端端点（`/web/*`）：JWT（python-jose），`POST /web/auth/login` 签发，5 demo 用户硬编码。
- 单一 `get_current_user` 依赖处理两层。

### 4. Mock 飞书适配器
`MockFeishuClient` 进程内模拟：写 `IntegrationAction` 行 -> 生成 fake `feishu_task_guid` -> `asyncio.create_task` 异步回调 `POST /v1/task/status`。`FEISHU_ORCHESTRATOR_MODE=mock|real` 切换。平台默认 mock 模式，无需真飞书即可全链路演示。

### 5. 状态机实现
通用 `StateMachine` 类，构造时传入 `{from_state: [allowed_to_states]}` 字典。`transition(obj, event, expected_from)` 方法校验前置条件并写入 `AuditEvent`。6 个领域状态机（候选决策、主张、参数版本、任务、结果、集成动作）各实例化一个。

### 6. 六道闸门为纯函数
`run_six_gates(candidate, db) -> OverallGateResult`。每闸门独立可测。`publishBtn` 调用时服务端运行；失败返回 409 + 失败闸门列表。

### 7. 一键修正生成 TaskRevision
阻断任务的修正**不静默覆盖**：创建新 `TaskDraft`（复制旧值，替换 parameter_version_id 为 active）-> 新 `Task` -> `TaskRevision` 链接新旧 -> 旧 `Task.status=blocked` 保留 -> 调 `feishu_client.create_task`。

### 8. 失败卡根因标记为假设
`FailureBoundary.is_assumption` 默认 `True`。`root_cause_hypothesis` 字段显式命名。符合 `openspec/specs/result-backflow/spec.md` 与 `feishu-actions` spec 对"假设"标记的要求。

### 9. 前端复用 HTML
复制 `附件/index.html` -> `app/static/index.html`，剥离内联 mock 脚本，加 `app.js` 调真实 API。视觉结构不变，`publishBtn`/`fixBtn`/`askBtn` 接线。docx 明确：「不要为换框架耽误主链路」。

### 10. 契约 schema 同源
`app/adapters/contract_validator.py` 启动时从 `feishu-orchestrator/feishu-orchestrator/contracts/*.schema.json` 只读加载，用 `jsonschema` 校验每个 `/v1/*` 请求体。双侧 schema 同源，避免漂移。

## Tech Stack

| 组件 | 选择 | 版本 |
|---|---|---|
| 框架 | FastAPI | 0.141 |
| ORM | SQLAlchemy | 2.0 |
| 迁移 | Alembic | 1.19 |
| 校验 | Pydantic | 2.13 |
| 配置 | pydantic-settings | latest |
| 数据库 | PostgreSQL | 16 |
| 驱动 | psycopg2-binary | 2.9 |
| 鉴权 | python-jose | latest |
| HTTP | httpx | latest（Mock 飞书回调 + 测试） |
| Schema | jsonschema | latest |
| 测试 | pytest + pytest-asyncio | latest |
| 容器 | Docker + Compose | 29.5 / v5.1 |

## Risks & Mitigations

- **PostgreSQL 测试依赖 Docker**：`conftest.py` 检测 `DATABASE_URL`，缺失时 skip 而非 fail；`scripts/run_dev.sh` 自动起 docker compose。
- **Mock 飞书异步回调时序**：测试用 `pytest-asyncio` + `asyncio.wait` 确保回调完成；生产用 `IntegrationAction.status` 轮询。
- **22 表迁移复杂度**：单个 `0001_initial.py` 建全表，避免多 revision 演进负担。
- **前端接线遗漏**：`app.js` 用显式元素 ID 映射表，每个按钮独立函数，便于回归测试覆盖。
