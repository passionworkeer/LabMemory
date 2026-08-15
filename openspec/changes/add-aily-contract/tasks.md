# Tasks: 接入 Aily 集成契约

## M1 - OpenSpec change

- [ ] 创建 change `add-aily-contract`（proposal + design + aily-contract spec 增量 + tasks）

## M2 - ID 映射层

- [ ] `app/db/models.py` 新增 `IntegrationRef` 模型（ref_type/aily_id 唯一/platform_type/platform_id/payload）
- [ ] `app/main.py` `_run_migrations` 加 `integration_refs` 建表迁移
- [ ] `app/api/aily.py` 内 helper：`_ref_get` / `_ref_put`（aily_id ↔ 平台实体互查）

## M3 - 10 个入站接口（app/api/aily.py，prefix=/v1，Bearer）

- [ ] POST /v1/transcripts（建会议+逐字稿，返回 transcript_id）
- [ ] POST /v1/extractions（存候选，返回 extraction_id + 各项 id）
- [ ] POST /v1/decision-inbox（返回 decision_id）
- [ ] POST /v1/decision-inbox/{id}/verdict（pass/reject → 复用确认+闸门逻辑）
- [ ] POST /v1/parameter-versions（签发主张，返回 version_id）
- [ ] POST /v1/preflight（跑 _run_checks，返回 ok/block + reasons + boundary_check）
- [ ] POST /v1/executions（回写结果，返回 execution_id）
- [ ] PATCH /v1/passports/{id}（更新 claim_state / failure_boundary）
- [ ] POST /v1/knowledge（发布，返回 knowledge_id）
- [ ] POST /v1/reverify-tasks（建复验任务，返回 reverify_id）

## M4 - 5 个出站 webhook（app/services/aily_webhook.py）

- [ ] `emit_event(event, payload)`：HMAC-SHA256 签名 + timestamp/nonce + 幂等键 + fire-and-forget
- [ ] 配置 `AILY_WEBHOOK_BASE_URL` / `AILY_WEBHOOK_SECRET` / `AILY_INTEGRATION_ENABLED`
- [ ] 触发点：decision.pending（meetings.py 复核待办）、preflight.blocked（tasks.py 审计阻断）、execution.deviated（results.py 冻结/偏差）、knowledge.ready（results.py 发布）、reverify.due（reverify-tasks 创建）

## M5 - 接线

- [ ] `app/config.py` 加 Aily 配置
- [ ] `app/main.py` 挂载 `aily_router`

## M6 - 验证

- [ ] 最小场景 curl：transcripts → extractions → decision-inbox → verdict(pass) → parameter-versions
- [ ] `pytest tests/ -q` 回归
- [ ] 出站 webhook 签名单元自检（本地直接调 emit_event 断言跳过/签名头）
