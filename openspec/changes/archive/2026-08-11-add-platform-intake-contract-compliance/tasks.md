# Tasks: 平台集成接口契约合规化

## M1 - OpenSpec change

- [x] 创建 change `add-platform-intake-contract-compliance`（proposal + design + platform-intake spec 增量 + tasks）
- [x] `openspec validate add-platform-intake-contract-compliance` 通过

## M2 - 鉴权与前缀

- [x] `app/api/deps.py` `verify_platform_api_key` 改双接受 `Authorization: Bearer` + `X-Platform-Api-Key`
- [x] `app/api/meetings.py` `v1_router` 前缀 `/v1` → `/api/v1`
- [x] `app/api/meetings.py` `receive_candidate` 响应补 `status:"submitted"` + `results[]` + `review_count`

## M3 - 服务层抽取

- [x] 新增 `app/services/review.py` `confirm_review_core(db, meeting, review, user, decision, modifications, notes) -> (claim, task)`
- [x] 新增 `app/services/audit.py` `run_audit_core(db, task, user) -> ActionAudit`（含六道闸门 `_run_checks` + 状态流转）
- [x] `app/api/meetings.py:confirm_review` 与 `app/api/tasks.py:run_audit` 改调 service（行为不变）

## M4 - 3 条新契约路由

- [x] `app/schemas.py` 加 `CardCallbackIn`（嵌套 action.value）、`TaskStatusIn`、候选详情响应
- [x] 新增 `app/api/integration.py`（挂 `/api/v1` + `verify_platform_api_key`）：
  - `GET /api/v1/candidates/{candidate_id}`（扁平 + 富化 meeting_title/source_url）
  - `POST /api/v1/task/status`（candidate_id→Task，写 feishu_task_guid）
  - `POST /api/v1/card/callback`（嵌套信封解析 + 按 action_type 分流 + 真实 action_audit）
- [x] `app/main.py` 挂载 integration 路由
- [x] `app/db/models.py` `Task` 加 `feishu_task_guid` 列；`app/main.py:_run_migrations` 补列迁移
- [x] `candidate_id` 解析 helper（扫 `Candidate.candidates` JSON）

## M5 - 夹具同步

- [x] `scripts/e2e_test.py`、`scripts/mock_feishu_push.py`：路由 `/v1/*`→`/api/v1/*`、鉴权头改 `Authorization: Bearer`
- [x] 重跑平台 `e2e_test` + pytest 确认绿

## M6 - 真跨侧 e2e

- [x] 新增 `scripts/cross_side_check.py`（urllib + Bearer，4 路由联动）
- [x] 跑 cross_side_check 全 200 + 字段断言
- [x] 编排器 `test_integration` 回归 22/22

## M7 - 归档与交付

- [x] `openspec validate --all` 全绿
- [x] 更新 `INTEGRATION.md` §6 合规对照表为全 ✅ + 新增跨侧 e2e 小节 + §5 前端 npm 定论
- [x] `openspec archive add-platform-intake-contract-compliance --yes`
- [x] `git add` + 中文 commit + `git push`
