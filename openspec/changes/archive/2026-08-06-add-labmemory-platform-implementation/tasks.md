# Tasks: LabMemory Platform Implementation

## M1 - 骨架与 OpenSpec change

- [x] 创建 OpenSpec change `add-labmemory-platform-implementation`（proposal + design + tasks + 4 spec 增量）
- [x] `openspec validate add-labmemory-platform-implementation` 通过
- [x] `pyproject.toml` 全依赖；补装 pydantic-settings/httpx/pytest/pytest-asyncio/jsonschema/python-jose/python-multipart/openpyxl 到 labmemory conda env
- [x] `app/db/base.py` 共享 Base + TimestampMixin + IDMixin
- [x] 重构 7 个现有模型 import 为 `from app.db.models.X`；统一 `app.db.models` 路径
- [x] `app/config.py`（pydantic-settings 读 .env）
- [x] `app/db/session.py` 重写（从 config 读 URL）
- [x] Alembic `env.py` 修 sys.path（相对路径，不硬编码）
- [x] `alembic.ini` 修 sqlalchemy.url 占位
- [x] `0001_initial.py` 建 22 表
- [x] `docker-compose.yml` + `Dockerfile`
- [x] `.gitignore`、`.env.example` 扩充、`README.md` 重写
- [x] `tests/conftest.py`（PostgreSQL test 库 fixture）
- [x] **可验证**：`docker compose up` 启动；`alembic upgrade head` 干净；`/health` 200

## M2 - 契约端点 + Mock 飞书

- [x] `app/schemas/{candidate,meeting,feishu_action,card_callback}.py` 对齐 JSON Schema
- [x] `app/adapters/contract_validator.py`（读 feishu-orchestrator/contracts/*.schema.json）
- [x] `app/api/v1/endpoints/candidates.py`：POST /v1/candidates + GET /v1/candidates/{id}
- [x] `app/api/v1/endpoints/callbacks.py`：POST /v1/card/callback 返回 {status, action_audit}
- [x] `app/api/v1/endpoints/task_status.py`：POST /v1/task/status
- [x] `app/api/deps.py`：get_db / get_current_user（Bearer 双层）/ require_role
- [x] `app/adapters/feishu_client.py`：MockFeishuClient + RealFeishuClient + factory
- [x] `app/core/state_machine.py`、`idempotency.py`、`audit_log.py`、`errors.py`
- [x] `tests/integration/test_contract_candidates.py`、`test_contract_callback.py`、`test_contract_task_status.py`
- [x] `tests/unit/test_state_machine.py`、`test_idempotency.py`
- [x] **可验证**：契约端点过 schema 校验；Mock 飞书 round-trip /v1/task/status

## M3 - 领域服务与状态机

- [x] 22 模型全字段 + 关系映射（修复 foreign_keys 歧义）
- [x] `app/services/gates.py`：六闸门（object/parameter/evidence/scope/state/responsibility）
- [x] `app/services/review.py`：三值留痕 + 语义分类
- [x] `app/services/version.py`：参数版本状态机 + 单 active 强制 + 替代链查找
- [x] `app/services/audit.py`：5 检查 + 3 态结论 + 旧版本阻断 + 一键修正
- [x] `app/services/task.py`：任务生命周期 + TaskRevision
- [x] `app/services/result.py`：回流 + 冻结 + 失败卡 + 非二元知识状态
- [x] `app/services/passport.py`：跨对象时间线聚合
- [x] `app/services/permissions.py`：5 角色 + 项目成员校验
- [x] `app/services/qa.py`：可信问答 + 拒答
- [x] `tests/unit/test_gates.py`、`test_audit_checks.py`、`test_version_uniqueness.py`、`test_freeze_logic.py`、`test_three_value.py`、`test_qa_refuse.py`
- [x] **可验证**：每条领域规则单测通过

## M4 - 前端端点 + 种子数据

- [x] `app/api/web/endpoints/auth.py`：login + me
- [x] `app/api/web/endpoints/review.py`：inbox 列表/详情/confirm/reject
- [x] `app/api/web/endpoints/audit.py`：task audit + fix
- [x] `app/api/web/endpoints/results.py`：result submit + failure-card
- [x] `app/api/web/endpoints/passport.py`：experiment timeline
- [x] `app/api/web/endpoints/control_tower.py`：KPIs + anomalies + retry
- [x] `app/api/web/endpoints/qa.py`：ask
- [x] `app/api/web/endpoints/versions.py`：version history + activate
- [x] `app/seeds/users.json`、`story_a.py`、`story_b.py`、`run_all.py`
- [x] `scripts/seed.py`
- [x] `tests/business/test_flow_decision_inbox.py`、`test_flow_action_audit.py`、`test_flow_result_backflow.py`
- [x] `tests/permission/test_permissions.py`（7 测试）
- [x] `tests/exception/test_exceptions.py`（7 测试）
- [x] **可验证**：`python -m scripts.seed --reset` 灌 Story A+B；3 demo 流 curl 通过

## M5 - 前端接线 + 收尾归档

- [x] 复制 `附件/index.html` -> `app/static/index.html`，剥 mock 处理器
- [x] `app/static/app.js` 接线 publishBtn/fixBtn/askBtn/submitResultBtn/auditBtn/passportBtn/login 等
- [x] `app/main.py` 挂 StaticFiles + FileResponse 根路由
- [x] 按 §验证计划 验证 3 demo 流（TestClient 全通过）
- [x] `tests/regression/test_contracts_jsonschema.py`（8 测试）
- [x] README 重写（架构、运行、demo 指南）
- [x] `openspec validate add-labmemory-platform-implementation`
- [x] `openspec archive add-labmemory-platform-implementation --yes`
- [x] **可验证**：`docker compose up` 一键启动可演示；3 demo 流从 UI 可复现；OpenSpec change 已归档

## 测试汇总

- **90 个自动化测试全部通过**（unit 50 + integration 14 + business 3 + permission 7 + exception 7 + regression 9）
- 3 条主线 demo 端到端验证：决策收件箱（0.8eq->待验证）、行动前审计（80℃->70℃ 阻断+一键修正）、结果回流（65℃->部分支持+失败卡）
