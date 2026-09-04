# LabMemory 平台 ←→ Aily 对接说明（草版）

> 本文档是给 Aily 侧联调用的接口口径。平台代码实现见 `labmemory-platform/app/api/aily.py`（入站）与 `app/services/aily_webhook.py`（出站）。
> 状态：**草版可联调**，字段以"最小字段"为准，未列字段平台会尽量兼容/忽略。

---

## 0. 全局约定

| 项 | 约定 |
|---|---|
| 鉴权 | `Authorization: Bearer {PLATFORM_API_KEY}`（平台也兼容 `X-Platform-Api-Key`，二选一即可） |
| Content-Type | `application/json`（请求/响应均 UTF-8） |
| 测试 token | `dev-platform-api-key-please-rotate`（dev 沙箱；生产需换） |
| 基址 | `https://efb806c6af660a.lhr.life`（localhost.run 临时域名，隧道重连即变，实时值见仓库根 `.tunnel-8081.url`；本地 `http://127.0.0.1:8081`） |
| 文档 | `GET {base}/docs`（Swagger，含全部 `/v1/*`） |
| 健康 | `GET {base}/health` |

**用户身份主键**：平台用 `user_id`（平台 `User.id`，整数）；业务唯一标识 `username`；飞书侧关联用 `feishu_user_id`（`ou_` 前缀，可空）。**平台没有 email / phone**。所有"人"字段请写 `user_id` 或 `username`。

**内置登录名（`assignee` / `reviewer` / `executor` 直接填这些 `username`）**：
- `pi` → 项目负责人 PI
- `lead` → 实验负责人 Lead
- `executor` → 执行人 Executor
- `admin` → 管理员

**跳转 URL 模板**（前端 SPA 路由）：
- 决策项 / 复核台：`{base}/review/{meeting_id}`
- 自检 / 审计结果：`{base}/audit/{task_id}`
- 结果 / 知识：`{base}/result/{task_id}`
- 护照：`{base}/passport/{experiment_id}`

---

## 1. 平台接收的 10 个接口（Aily → 平台）

### 1.1 `POST /v1/transcripts` 收妙记/逐字稿
请求（最小）：
```json
{
  "meeting_id": "meet_xxx",
  "note_id": "minutes_xxx",
  "speakers": ["陈博士", "王工"],
  "segments": [
    {"start": 0, "end": 10, "speaker": "陈博士", "text": "70℃ 收率更好"}
  ],
  "experiment_id": "EXP-DEMO-001"
}
```
返回：`{"transcript_id": "meet_xxx", "meeting_id": "meet_xxx", "created": true}`

> **`experiment_id` 建议必传**：平台会议必须归属实验；缺失时回退 `EXP-DEMO-001`（仅沙箱）。

### 1.2 `POST /v1/extractions` Aily 抽取结果回写
请求（最小）：
```json
{
  "transcript_id": "meet_xxx",
  "params": [{"name": "temperature", "value": "70", "unit": "℃"}],
  "disputes": [],
  "risks": [],
  "task_candidates": [],
  "scope": {"material": "Compound-A"},
  "evidence": [{"speaker": "陈博士", "text": "70℃ 收率更好"}]
}
```
返回：`{"extraction_id": "EXT_xxx", "created": true, "candidate_ids": ["CDR_xxx"]}`

> **`scope` 强烈建议必传**：平台六道闸门有"范围门"，缺 `scope` 会判定 `pending_supplement`，无法签发正式版本（见 1.4/1.5）。

### 1.3 `POST /v1/decision-inbox` 创建待人工复核项
请求（最小）：
```json
{"extraction_id": "EXT_xxx", "assignee": "pi", "jump_url": "https://..."}
```
返回：`{"decision_id": "DEC_xxx", "meeting_id": "meet_xxx", "jump_url": "..."}`

### 1.4 `POST /v1/decision-inbox/{decision_id}/verdict` 复核裁决
请求（最小）：
```json
{"verdict": "pass", "reviewer": "pi", "comment": "同意", "verdict_at": "2026-08-14T00:00:00Z"}
```
- `verdict`：`pass` / `reject`
- 返回（pass，六道闸门全过）：
```json
{"ack": true, "decision_id": "DEC_xxx", "verdict": "pass",
 "version_id": "C_xxx", "task_id": "T_xxx", "publish_status": "current", "gate_report": []}
```
- 返回（pass，但闸门未过，**诚实阻断**）：
```json
{"ack": true, "decision_id": "DEC_xxx", "verdict": "pass",
 "version_id": "C_xxx", "task_id": null, "publish_status": "pending_supplement",
 "gate_report": ["scope: 范围门：材料/浓度/设备/批次等边界不明确"]}
```

### 1.5 `POST /v1/parameter-versions` 签发正式参数版本
请求（最小）：
```json
{"decision_id": "DEC_xxx", "params": [{"name": "temperature", "value": "70", "unit": "℃"}], "effective_from": "2026-08-14T00:00:00Z", "evidence_refs": []}
```
返回：`{"version_id": "C_xxx", "created": true, "publish_status": "current"}`

> 若该决策已在 1.4 生成版本，本接口幂等返回相同 `version_id`（`created:false`）。

### 1.6 `POST /v1/preflight` 执行前自检
请求（最小）：
```json
{"version_id": "C_xxx", "executor": "executor", "planned_at": "2026-08-14T00:00:00Z"}
```
返回：`{"verdict": "ok" | "block", "reasons": [...], "boundary_check": {...}, "task_id": "T_xxx"}`

### 1.7 `POST /v1/executions` 实际执行结果回写
请求（最小）：
```json
{"version_id": "C_xxx", "actual_params": {"temperature": "70"}, "results": {"yield": 78}, "executor": "executor", "executed_at": "2026-08-14T00:00:00Z"}
```
返回：`{"execution_id": "R_xxx", "status": "submitted" | "frozen", "created": true}`
- `frozen`：`actual_params` 的 key 与计划参数不一致（版本偏差）

### 1.8 `PATCH /v1/passports/{passport_id}` 更新护照/主张状态/失败边界
`passport_id` = 平台 `experiment_id`。请求（最小）：
```json
{"status": "active", "failure_boundary": {"phenomenon": "...", "root_cause_status": "待验证"}, "claim_state": "supported"}
```
返回：`{"passport_id": "EXP-DEMO-001", "experiment_id": "EXP-DEMO-001", "updated": true}`

### 1.9 `POST /v1/knowledge` 知识发布（元数据）
请求（最小）：
```json
{"passport_id": "EXP-DEMO-001", "title": "70℃ 已验证", "summary": "收率 78%", "doc_refs": []}
```
返回：`{"knowledge_id": "R_xxx", "title": "70℃ 已验证", "status": "published"}`
> 当前按"该护照下最新一条已提交结果"发布；如需指定某条执行结果，请后续用 `execution_id` 明确（口径待对齐）。

### 1.10 `POST /v1/reverify-tasks` 创建复验任务
请求（最小）：
```json
{"passport_id": "EXP-DEMO-001", "assignee": "executor", "due_at": "2026-08-20T00:00:00Z", "criteria": ["yield > 75"]}
```
返回：`{"reverify_id": "RV_xxx", "task_id": "RV_xxx"}`

---

## 2. 平台推给 Aily 的 5 个 Webhook 事件

> 目标地址 `{AILY_WEBHOOK_BASE_URL}/webhooks/{event}`，平台配置 `AILY_WEBHOOK_BASE_URL` / `AILY_WEBHOOK_SECRET`。
> 默认 `AILY_INTEGRATION_ENABLED=false`（不真推）；联调时设为 `true`。
> **本次联调验签密钥 `AILY_WEBHOOK_SECRET` = `7bacd375e4bb4fe48c6146cbdfd53a535a1a2d9090a340129fbffa5cbf57fb62`**（Aily 用它验签）。

**签名头（HMAC-SHA256）**：
- `X-LabMemory-Signature` = `hex(hmac_sha256(secret, timestamp + nonce + raw_body))`
- `X-LabMemory-Timestamp`（秒级时间戳）
- `X-LabMemory-Nonce`（随机串）
- `X-LabMemory-Idempotency-Key`（幂等键，Aily 用它去重）

| 事件 | 触发时机 | 最小 payload |
|---|---|---|
| `decision.pending` | 决策项创建 | `{decision_id, transcript_id, extraction_id, assignee, jump_url}` |
| `preflight.blocked` | 自检不通过 | `{preflight_id, version_id, reasons[], executor, jump_url}` |
| `execution.deviated` | 实际参数 vs 版本偏差超阈 | `{execution_id, version_id, diff{}}` |
| `knowledge.ready` | 知识可发布 | `{knowledge_id, passport_id, jump_url}` |
| `reverify.due` | 复验任务创建（到期自动触发暂缺，后续补定时器） | `{reverify_id, passport_id, assignee, due_at}` |

---

## 3. 最小联调场景建议

```
1 场会议 → 1 个参数抽取 → 1 条决策 → 1 个版本 → Aily 建 1 条飞书任务
链路：POST /v1/transcripts → /v1/extractions → /v1/decision-inbox
      → /v1/decision-inbox/{id}/verdict(pass) → /v1/parameter-versions
```

满足 `experiment_id` + `scope` 后，1.4 会返回 `publish_status=current` + `version_id` + `task_id`，Aily 即可凭返回值去飞书建任务。

---

## 4. 当前边界（诚实声明）

- **沙箱非公网**：`127.0.0.1:8081` 仅本机/局域网；Aily 异地联调需平台部署到公网或内网穿透。
- **草版字段**：`verdict_at` / `effective_from` / `evidence_refs` / `doc_refs` / `passports.status` 当前已接收但业务影响有限，口径待与 Aily 对齐。
- **knowledge 指定结果**：现按护照下最新结果发布；若需精确到 `execution_id`，需对齐字段。
- **reverify 到期自动触发**：平台暂无调度器，先手动/创建时触发。
