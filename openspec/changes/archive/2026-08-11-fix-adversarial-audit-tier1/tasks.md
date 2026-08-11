# Tasks: 对抗审查 Tier 1 修复

## M1 - OpenSpec change
- [x] 创建 change `fix-adversarial-audit-tier1`（proposal + design + 6 spec 增量 + tasks）
- [x] `openspec validate fix-adversarial-audit-tier1` 通过

## M2 - 平台安全（组 A）
- [x] `app/config.py`：默认密钥告警（model_validator warning）；CORS 默认白名单
- [x] `app/main.py`：CORS `*`+credentials 互斥降级
- [x] `app/api/meetings.py`：`GET /api/meetings`、`/{id}`、`/chain` 成员可见域过滤
- [x] `app/api/tasks.py`：`GET /{id}`、`/audit/compare` 加 `ensure_experiment_member`
- [x] `app/api/control_tower.py`：跨实验聚合加成员过滤
- [x] `app/api/admin.py`：`reset-demo` 限 admin
- [x] `app/api/results.py`：`publish_result` 强制成员校验

## M3 - 平台正确性（组 B，含我引入的 3 bug）
- [x] `app/main.py`：`tasks_new` 重建加 `feishu_task_guid` + 显式列名 INSERT
- [x] `app/api/integration.py`：`_actor_for` 不回退 admin；`card_callback` approve 不回退 running/completed
- [x] `app/api/tasks.py`：approve/reject/start 状态守卫；audit_fix 重复锁；`_run_checks` current=None 判 blocked
- [x] `app/api/deps.py`：`verify_platform_api_key` 用 `compare_digest`

## M4 - 编排器 real 模式契约对齐（组 C）
- [x] `core/platform_client.py`：新增 `submit_meeting`
- [x] `core/pipeline_orchestrator.py`：编译前先 POST /api/v1/meetings；metadata 注入 experiment_id；source_package_id==meeting_id
- [x] `adapters/minutes_adapter.py`、`adapters/aily_adapter.py`：metadata.experiment_id + id 统一

## M5 - 编排器可靠性（组 D）
- [x] `reliability/idempotency.py`：`O_CREAT|O_EXCL` 原子占位
- [x] `core/card_handler.py`：needs_confirmation/revise/blocked 分支 + 不静默 success；forward 成功后立即 mark
- [x] `adapters/aily_adapter.py`：无条件强制 status=candidate/needs_review=True
- [x] `core/webhook_server.py` + `core/config.py`：RUN_MODE mock 限 localhost + 大 warning
- [x] `core/platform_client.py` + 夹具 + tests：删 "approved" 兼容，统一 "approve"
- [x] `mock/mock_server.py`：字段对齐嵌套契约 + feishu_task_guid
- [x] `reliability/retry_engine.py` + `platform_client._http_post`：保留 HTTP code 判 5xx/429

## M6 - 小修（组 E）
- [x] `core/event_router.py`：meeting.ended/minutes 乱序兜底；空 event_id 幂等兜底
- [x] `core/webhook_server.py`：url_verification 移到验签后
- [x] `core/card_handler.py`：get_candidate fallback 缺字段→报错

## M7 - 验证与归档
- [x] 平台 e2e + pytest + cross_side_check 全绿
- [x] 编排器 test_integration 全绿（"approve" 统一后更新断言）
- [x] 迁移旧库模拟不崩
- [x] `openspec validate --all` 全绿
- [x] 写 `AUDIT.md` Tier 2 路线图
- [x] `openspec archive fix-adversarial-audit-tier1 --yes`
- [x] `git add` + 中文 commit + `git push`
