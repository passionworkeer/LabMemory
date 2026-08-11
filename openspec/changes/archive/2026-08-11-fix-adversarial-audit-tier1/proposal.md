# Proposal: 对抗审查 Tier 1 缺陷修复（安全/正确性/契约对齐/可靠性）

## Why

对整个项目做了三维度对抗 + 第一性原理审查（平台正确性/安全、第一性原理/规格一致性、编排器/跨侧接线），发现一批真实缺陷：2 个 P0 安全/迁移、3 个 B 计划引入的 bug、编排器 real 模式契约对齐的 3 个 P0、幂等 TOCTOU 竞态、审计未过静默 success 等。本 change 修复全部**有界缺陷**（Tier 1，~28 条），缺失功能（Tier 2，六闸门/冲突检测/证据降级等）另记路线图（`AUDIT.md`），不在本 change 范围。

## What Changes

**平台安全与越权**：
- `JWT_SECRET`/`PLATFORM_API_KEY` 为默认值时启动 warning（不 crash，保 dev/test）。
- CORS 默认改白名单（`localhost:5173/8081`），禁 `*`+credentials 共存。
- `GET /api/tasks/{id}`、`/audit/compare`、`GET /api/meetings*` 加实验成员可见域过滤（admin/pi 全局可见）。
- `admin.reset-demo` 限制 admin；`publish_result` 强制成员校验。

**平台正确性（含 B 计划引入的 3 个 bug）**：
- 迁移 `tasks_new` 重建改显式列名 + 加 `feishu_task_guid`（修 `SELECT *` 列错位/启动崩）。
- `_actor_for` open_id 不可解析返 None（不充当 admin）。
- `card_callback` approve 不回退 running/completed 任务状态（仅 draft/needs_confirmation/blocked 可审计；processed 幂等返回）。
- approve_task/start_task/audit_fix 状态守卫；`_run_checks` 版本门 current_claim=None 判 blocked；`verify_platform_api_key` 常量时间比较。

**编排器 real 模式契约对齐（P0）**：
- `platform_client` 新增 `submit_meeting`；pipeline 编译前先 `POST /api/v1/meetings`。
- `MeetingPackage.metadata` 注入 `experiment_id`（CLI 参数/映射）。
- candidate `source_package_id` == 已注册会议 `meeting_id`。

**编排器可靠性（P0/first-principles）**：
- 幂等 `mark` 改 `O_CREAT|O_EXCL` 原子占位，消除 TOCTOU。
- `card_handler` 增 needs_confirmation/revise 显式分支 + default→blocked，不再静默 success；forward 成功后立即 mark。
- Aily 无条件强制 `status=candidate, needs_review=True`。
- RUN_MODE 默认 mock 但限 localhost + 大 warning；`"approved"` 统一为 `"approve"`；mock_server 字段对齐嵌套契约；retry 保留 HTTP code 判 5xx/429。

**小修（P2）**：meeting.ended/minutes 乱序、空 event_id 幂等兜底、url_verification 验签顺序、get_candidate fallback、control_tower 成员过滤。

## Impact

- spec 增量：MODIFY `platform-permissions`、`platform-intake`、`trust-rules`、`meeting-ingest`、`orchestration-reliability`、`feishu-actions`。
- 平台改动：`config.py`、`main.py`、`api/deps.py`、`api/integration.py`、`api/tasks.py`、`api/meetings.py`、`api/results.py`、`api/admin.py`、`api/control_tower.py`。
- 编排器改动：`core/platform_client.py`、`core/pipeline_orchestrator.py`、`core/card_handler.py`、`core/config.py`、`core/webhook_server.py`、`core/event_router.py`、`adapters/aily_adapter.py`、`adapters/minutes_adapter.py`、`reliability/idempotency.py`、`reliability/retry_engine.py`、`mock/mock_server.py`、`tests/test_integration.py`。
- 测试夹具：`scripts/e2e_test.py`、`scripts/mock_feishu_push.py`（"approve" 统一）。
- 回归守护：平台 e2e 17 步、pytest、cross_side_check 5/5、编排器 test_integration 全绿（部分断言随契约统一更新）。
