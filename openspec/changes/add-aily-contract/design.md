# Design: 接入 Aily 集成契约

## 目标与约束

- 让 Aily 侧通过 10 个 `/v1/*` 入站接口 + 5 类出站 webhook 对接平台，最小场景 `1→2→3→4→5` 先跑通。
- 复用现有领域逻辑，不重写六道闸门/版本/审计/结果/护照核心。
- 不破坏现有 `/api/v1/*` 契约与前端。
- 鉴权：Bearer Token（`verify_platform_api_key`，双接受 Bearer / X-Platform-Api-Key）。

## 关键决策

### D1 路径与鉴权：`/v1/*` + Bearer
Aily 契约路径无 `/api` 前缀，因此新建 `app/api/aily.py` 的 `aily_router = APIRouter(prefix="/v1", dependencies=[Depends(verify_platform_api_key)])`，与现有 `/api/v1/*` 并存，互不影响。所有入站请求用 `Authorization: Bearer {PLATFORM_API_KEY}`。

### D2 ID 映射：`integration_refs` 表（不污染领域模型）
Aily 侧 ID（transcript/extraction/decision/version/execution/passport/knowledge/reverify）与平台实体用一张轻量表映射，避免在领域表加一堆外键列：

```
IntegrationRef(id PK, ref_type, aily_id unique, platform_type, platform_id, payload JSON)
```

- `transcript_id` → `Meeting.meeting_id`
- `extraction_id` → `Candidate.source_package_id`（约定为 meeting_id）+ 第一个候选 `candidate_id`
- `decision_id` → `MeetingReview`（platform_id = meeting_id，一会议一决策项）
- `version_id` → `Claim.claim_id`
- `execution_id` → `Result.result_id`
- `passport_id` → `Experiment.experiment_id`
- `knowledge_id` → 已发布 `Result.result_id`
- `reverify_id` → `Task.task_id`（复验任务）

### D3 experiment 归属：`/v1/transcripts` 接受可选 `experiment_id`
Aily 的 transcript 最小字段不含实验归属，但平台 `Meeting` 必填 `experiment_id`。约定：`/v1/transcripts` 请求体额外接受 `experiment_id`（或 `metadata.experiment_id`），缺失时回退到 `EXP-DEMO-001`（demo 沙箱）；真实环境由 Aily 传入。此口径在 OpenAPI 文档中显式标注。

### D4 入站接口复用现有逻辑
- `POST /v1/transcripts` → 组装 `MeetingPackageIn` → 复用 `receive_meeting` 逻辑建 Meeting + 自动建 pending 复核。
- `POST /v1/extractions` → 组装 `CandidatePackageIn` → 复用 `receive_candidate` 逻辑。
- `POST /v1/decision-inbox` → 确保/返回 `MeetingReview(pending)` 的 `decision_id`。
- `POST /v1/decision-inbox/{id}/verdict` → `approve` 走 `_build_claim`+六道闸门+建任务草稿（复用 `integration.py:card_callback` 的 approve 分支），`reject` 走 ended。
- `POST /v1/parameter-versions` → 用 decision 的候选+参数 `_build_claim` 签发 `current` 主张，返回 `version_id=claim_id`。
- `POST /v1/preflight` → 找到 version 对应任务跑 `_run_checks`，返回 ok/block + reasons + boundary_check。
- `POST /v1/executions` → 复用 `submit_result` 逻辑回写结果，偏差（actual vs planned key 不一致）记 frozen。
- `PATCH /v1/passports/{id}` → 更新实验当前主张 `knowledge_status` / 失败边界（写到当前结果或主张）。
- `POST /v1/knowledge` → 复用 `publish_result` 逻辑发布知识。
- `POST /v1/reverify-tasks` → 复用 `audit_fix`/新建任务逻辑生成复验任务。

### D5 出站 webhook：HMAC-SHA256 + 幂等键
新增 `app/services/aily_webhook.py`：
- 目标 `{AILY_WEBHOOK_BASE_URL}/webhooks/{event}`（可配）。
- 签名：`X-LabMemory-Signature = hex(hmac_sha256(secret, timestamp + nonce + raw_body))`，附 `X-LabMemory-Timestamp`、`X-LabMemory-Nonce`、`X-LabMemory-Idempotency-Key`（幂等键 = `{event}:{业务ID}`）。
- fire-and-forget：失败只记日志；`AILY_INTEGRATION_ENABLED != "true"` 时不真调（默认关闭，避免本地误发）。
- 触发点：decision.pending（复核待办创建）、preflight.blocked（审计阻断）、execution.deviated（结果冻结/偏差）、knowledge.ready（发布）、reverify.due（复验任务创建，无定时器，先手动触发）。

### D6 复验到期（reverify.due）
平台无调度器，先提供 `POST /v1/reverify-tasks` 与手动触发 webhook 的能力；到期自动触发留待后续（另起 change）。

## 非目标

- 不做真飞书任务/卡片/知识库落地（由 Aily 拿到接口返回值后自行调飞书，见契约注）。
- 不做公网沙箱部署（代码外工作）。
- 不引入定时调度框架。
- 不改现有 `/api/v1/*` 契约与前端业务。

## 风险

- **ID 口径**：Aily 侧 ID 与平台 ID 语义需对齐；用 `integration_refs` 解耦，任何一方字段调整只改映射层。
- **experiment 归属缺失**：transcript 无 experiment 时回退 demo 实验，真实环境需 Aily 传入，否则数据落到错误实验。
- **回归**：新增路由/表/配置为追加式，不触碰现有逻辑；pytest 回归守护。
