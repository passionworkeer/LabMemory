# Proposal: 接入 Aily 集成契约（10 入站 + 5 出站 webhook）

## Why

Aily 侧要与平台打通，给出了新契约：平台**收** 10 个 HTTP 接口（逐字稿/抽取/决策项/版本/自检/执行/护照/知识/复验），平台**推** 5 类 webhook 事件（带 HMAC 签名 + 幂等键）。当前平台只有更粗的 `/api/v1/*`（meetings/candidates/card-callback/task-status）与请求/响应式反向联动，**没有**这套细粒度 ID（transcript/extraction/decision/version/execution/passport/knowledge/reverify）与签名 webhook，无法直接对接 Aily。

## What Changes

- **新增** `app/db/models.py` 的 `IntegrationRef` 映射表 + 迁移：把 Aily 侧 ID（`aily_id`）与平台实体（`meeting_id`/`claim_id`/`task_id`/`result_id`/`experiment_id`/复核记录）一一对应，避免污染领域模型。
- **新增** `app/api/aily.py`：`/v1/*` 前缀 + `verify_platform_api_key`（Bearer Token）的 10 个入站接口，复用既有领域逻辑（`receive_meeting`/`receive_candidate`/`_build_claim`/`_run_checks`/`submit_result`/`publish_result`）。
- **新增** `app/services/aily_webhook.py`：5 类出站事件，HMAC-SHA256 签名头（`X-LabMemory-Signature` + timestamp/nonce）+ 幂等键（`X-LabMemory-Idempotency-Key`），fire-and-forget。
- **修改** `app/config.py`：新增 `AILY_WEBHOOK_BASE_URL` / `AILY_WEBHOOK_SECRET` / `AILY_INTEGRATION_ENABLED`。
- **修改** `app/main.py`：挂载 `aily` 路由 + `IntegrationRef` 建表迁移。
- **修改** 业务节点：在对应状态变化点触发 5 个出站 webhook（非阻断）。
- **不修改** 现有 `/api/v1/*` 契约、前端、六道闸门审计逻辑、实验护照只读聚合语义（护照写入口走 `IntegrationRef` 映射 + 允许更新失败边界/主张状态）。

## Impact

- 1 个新 spec 领域增量（`aily-contract`，ADDED 需求）。
- 新增 `app/api/aily.py`、`app/services/aily_webhook.py`、`app/db/models.py`（加 `IntegrationRef`）、`app/config.py`、`app/main.py`（迁移+挂载）。
- 业务节点改动：`app/api/meetings.py`（decision.pending）、`app/api/tasks.py`（preflight.blocked / execution.deviated）、`app/api/results.py`（knowledge.ready）。
- 最小场景：`1 会议 → 1 抽取 → 1 决策 → 1 版本 →（Aily 建飞书任务）`可端到端跑通；reverify.due 因平台无定时器，先提供接口与手动触发入口。
