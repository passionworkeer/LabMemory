# Proposal: 平台集成接口契约合规化（打通飞书编排器实时联动）

## Why

`openspec/specs/contracts/spec.md`「平台集成接口路径」已冻结：基址 `PLATFORM_API_BASE`（默认含 `/api`）、4 条路由 `POST /v1/candidates`、`POST /v1/card/callback`、`POST /v1/task/status`、`GET /v1/candidates/{candidate_id}`、鉴权 `Authorization: Bearer {PLATFORM_API_KEY}`。`feishu-orchestrator` 完全合规。

但 `labmemory-platform` 偏离契约 5 处，导致把真实编排器指向真实平台时**全部 403 / 404**，实时跨侧联动不可用：

1. **鉴权头**：`app/api/deps.py:77` `verify_platform_api_key` 只认 `X-Platform-Api-Key`，不认契约要求的 `Authorization: Bearer`。
2. **base 路径**：`app/api/meetings.py:39` `v1_router` 挂在根 `/v1`，而编排器 `PLATFORM_API_BASE` 默认含 `/api`，拼出 `/api/v1/candidates`。
3. **缺路由**：契约 4 条里平台只实现了 `POST /v1/candidates`；缺 `card/callback`、`task/status`、`GET /candidates/{id}`。
4. **候选响应缺 `status`**：编排器 `pipeline_orchestrator.py:80` 读响应 `status` 键，而平台 `receive_candidate` 只回 `{id, created}`。
5. **无 `candidate_id → 业务对象` 解析**：卡片回调与候选详情按 `candidate_id` 定位，平台 `Candidate.candidates` 是 JSON 数组、无索引，无法定位 meeting/task。

两侧当前各自对着对方的 Mock 跑通（A 计划已验证），但「整合两边、确保整个可用」要求把平台拉回契约合规、补齐联动路由。

## What Changes

- **新增** 平台侧 `platform-intake` 领域规格：定义 `/api/v1` 下 4 条集成路由的鉴权、路径、请求/响应与行为。
- **修改** `app/api/deps.py` `verify_platform_api_key`：**双接受** `Authorization: Bearer {key}` 与 `X-Platform-Api-Key`（过渡期兼容既有平台夹具，零破坏）。
- **修改** `app/api/meetings.py`：`v1_router` 前缀 `/v1` → `/api/v1`；`receive_candidate` 响应补 `status:"submitted"` + `results[]` + `review_count`。
- **新增** `app/api/integration.py`：3 条契约路由挂在 `/api/v1` + `verify_platform_api_key`：
  - `GET /api/v1/candidates/{candidate_id}`：扫 `Candidate.candidates` JSON 定位，返回**扁平**候选对象，富化 `meeting_title` + `source_url`。
  - `POST /api/v1/task/status`：按 `candidate_id` → Candidate → meeting → 最新 Task，写 `feishu_task_guid`，记 status；snake_case 字段。
  - `POST /api/v1/card/callback`：解析**嵌套**飞书信封 `action.value.{action_type, candidate_id}` + `open_id` + `token`（幂等）；`approve`→复核确认+六道闸门审计、`reject`→结束、`revise`→阻断；返回 `{status, action_audit, candidate_id, message}`，`action_audit` 取**真实**审计结论。
- **新增** `app/services/review.py` 与 `app/services/audit.py`：把 `meetings.py:confirm_review` 与 `tasks.py:run_audit` 的核心逻辑抽成可复用 service，供 JWT 端点与新 `/api/v1/card/callback` 共用（行为不变，回归守护）。
- **修改** `app/db/models.py` `Task`：加列 `feishu_task_guid`；`app/main.py:_run_migrations` 补列迁移。
- **修改** `app/schemas.py`：加 `CardCallbackIn`（嵌套）、`TaskStatusIn`、候选详情响应结构。
- **修改** 平台测试夹具 `scripts/e2e_test.py`、`scripts/mock_feishu_push.py`：路由 `/v1/*` → `/api/v1/*`，鉴权头统一改 `Authorization: Bearer`（示范契约写法）。
- **新增** `scripts/cross_side_check.py`：以编排器同款 `urllib` + `Authorization: Bearer` 打本地平台，端到端验证 4 路由联动。
- **不修改** `feishu-orchestrator/`（编排器已合规）、`openspec/specs/contracts/`（契约冻结）、六道闸门审计逻辑、知识状态计算、前端业务逻辑。

## Impact

- 1 个新 spec 领域增量（`platform-intake`，ADDED 6 需求）。
- 后端改动：`deps.py`、`meetings.py`、`tasks.py`（改调 service）、新 `integration.py`、新 `services/review.py` + `services/audit.py`、`models.py`、`main.py`（迁移）、`schemas.py`。
- 夹具改动：`scripts/e2e_test.py`、`scripts/mock_feishu_push.py`。
- 新增：`scripts/cross_side_check.py`。
- 现有平台 e2e_test / pytest / 编排器 test_integration 在路由前缀与鉴权头同步后仍全绿（回归守护）。
- 真实飞书凭证仍为占位符：真飞书侧端到端（妙记事件 → webhook）需配 `FEISHU_APP_ID/SECRET` + `AILY_API_KEY` + `RUN_MODE=real`；本次跨侧 e2e 用编排器同款客户端直打平台证明联动通路，不依赖真飞书凭证。
