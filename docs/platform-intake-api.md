# LabMemory 平台接入 API

> 面向外部系统（Aily / 飞书编排器 / 自建脚本）向平台推送会议纪要与候选决策。
> 权威来源：在线 Swagger `{BASE_URL}/docs`、契约规格 `openspec/specs/contracts/spec.md`、
> JSON Schema `labmemory-platform/app/contracts/*.schema.json`。

## 通用约定

- Base URL：`http://127.0.0.1:8081/api`（生产替换域名，**路径必须保留 `/api`**）
- 方式：HTTP POST + JSON body（`GET` 不支持，会被前端 catch-all 路由返回 404）
- 认证：`Authorization: Bearer <PLATFORM_API_KEY>`，或等价的 `X-Platform-Api-Key: <同一值>`
  （实现见 `app/api/deps.py:107`）
- 编码：`Content-Type: application/json`，UTF-8
- 时间：ISO 8601 带时区，如 `2026-08-15T17:00:00+08:00`

错误响应统一格式（`app/core/errors.py`）：

```json
{"code": "not_found", "message": "实验不存在：EXP-X（请先由 PI 创建实验）", "details": {}}
```

| code | HTTP | 典型原因 |
|---|---|---|
| `permission_denied` | 403 | API Key 缺失或错误 |
| `not_found` | 404 | 实验/会议/候选不存在 |
| `validation_failed` | 422 | 必填字段缺失或类型不符 |
| `conflict` / `invalid_state` | 409 | 重复资源 / 状态不允许该操作 |

## 调用顺序

```
POST /api/v1/meetings      纪要入库，自动生成 pending 复核
POST /api/v1/candidates    候选决策入库（source_package_id = meeting_id）
  → 人工在平台前端或飞书卡片确认
POST /api/v1/card/callback  卡片审批回调（可选）
POST /api/v1/task/status    飞书任务建好后回写 guid
```

顺序不可颠倒：候选依赖会议先入库。只推纪要不推候选也是合法用法。

---

## 1. POST /api/v1/meetings — 推送会议纪要

实现：`labmemory-platform/app/api/meetings.py:42`

请求体：

```json
{
  "schema_version": "1.0.0",
  "source": "aily",
  "source_object_id": "minutes_20260815_001",
  "meeting_id": "meet_20260815_001",
  "title": "Compound-A 温度参数评审会",
  "start_time": "2026-08-15T14:00:00+08:00",
  "end_time": "2026-08-15T15:00:00+08:00",
  "organizer": "陈博士",
  "participants": ["陈博士", "王工程师"],
  "content": {
    "summary": "决定把反应温度从 70℃ 调到 75℃，下周出小试结果",
    "transcript": [
      {"speaker": "陈博士", "start_offset_sec": 0, "end_offset_sec": 12, "text": "上一轮 70℃ 转化率偏低"},
      {"speaker": "王工程师", "start_offset_sec": 15, "end_offset_sec": 28, "text": "建议升到 75℃ 试一轮"}
    ]
  },
  "source_url": "https://xxx.feishu.cn/minutes/obcnxxxx",
  "captured_at": "2026-08-15T15:05:00+08:00",
  "metadata": {"experiment_id": "EXP-DEMO-001"}
}
```

必填字段：

- `source_object_id` — 上游对象 ID（妙记 token 等）
- `meeting_id` — 会议唯一 ID，**幂等键**
- `title` — 会议标题
- `content` — 对象；平台只解析 `summary`（字符串）与 `transcript`（数组，元素
  `{speaker, start_offset_sec, end_offset_sec, text}`），其余键原样存入 `raw_payload`。
  只有 `summary` 没 `transcript` 也可推送
- `captured_at` — 采集时间
- `metadata.experiment_id` — 必须是平台已存在的实验，否则 404

可选字段：`schema_version`（默认 `1.0.0`）、`source`（默认 `feishu_minutes`，自定义来源不校验）、
`start_time`、`end_time`、`organizer`、`participants`、`source_url`。

> 无 `receiver` / `timestamp` 字段：投递对象由 `metadata.experiment_id` 决定，时间字段名为 `captured_at`。

响应 200：

```json
{"meeting_id": "meet_20260815_001", "id": 17, "created": true}
```

副作用：自动创建 `status=pending` 的复核记录，会议进入「会后复核」列表。
重复推同一 `meeting_id` 返回 `created: false`，且**不覆盖**原内容（`meetings.py:51-54`）。

---

## 2. POST /api/v1/candidates — 推送候选决策

实现：`app/api/meetings.py:81`

```json
{
  "schema_version": "1.0.0",
  "source_package_id": "meet_20260815_001",
  "aily_skill_version": "aily-labmemory-v1.0",
  "candidates": [{
    "candidate_id": "CDR-20260815-001",
    "type": "parameter_change",
    "title": "温度 70→75℃",
    "description": "提升收率",
    "experiment_ref": "EXP-DEMO-001",
    "parameters": [{"name": "temperature", "value": "75", "unit": "℃"}],
    "confidence": 0.85,
    "evidence": [{"speaker": "王工程师", "text": "建议升到 75℃ 试一轮", "start_offset_sec": 15}],
    "status": "pending_review",
    "needs_review": true
  }],
  "risks": [],
  "action_items": [],
  "open_questions": ["75℃ 副产物是否可控"],
  "compiled_at": "2026-08-15T15:06:00+08:00"
}
```

- `source_package_id` 必填，**必须等于会议的 `meeting_id`**，否则 404
- `type` 取值：`decision` / `conclusion` / `risk` / `action_item` / `question` / `parameter_change`
- 溯源字段可选：`aily_skill_version` / `model_version` / `prompt_version` / `input_hash` / `raw_output`

响应 200：

```json
{
  "id": 15, "created": true, "status": "submitted",
  "results": [{"candidate_id": "CDR-20260815-001", "status": "pending_review"}],
  "review_count": 4
}
```

副作用：`needs_review` 的候选取前 3 个，请求飞书侧下发复核卡片（fire-and-forget，
失败不影响本次响应，`meetings.py:268`）。

---

## 3. GET /api/v1/candidates/{candidate_id} — 查候选详情

实现：`app/api/integration.py:60`。返回扁平对象，额外富化 `meeting_title` / `source_url`
（供编排器拼飞书任务摘要）。字段：`candidate_id`、`type`、`title`、`description`、
`experiment_ref`、`parameters`、`evidence`、`confidence`、`status`、`needs_review`、
`assignee`、`due_date`、`meeting_title`、`source_url`。

> 实现为全表扫 `Candidate.candidates` JSON（`integration.py:38-48`），demo 规模够用；
> 生产规模需加 `candidate_id` 索引列。

---

## 4. POST /api/v1/card/callback — 转发卡片审批回调

实现：`app/api/integration.py:113`

```json
{
  "token": "callback_token_unique",
  "open_id": "ou_xxx",
  "action": {"value": {"action_type": "approve", "candidate_id": "CDR-20260815-001"}}
}
```

`action_type` 仅接受 `approve` / `revise` / `reject`。响应：

```json
{"status": "blocked", "action_audit": "needs_confirmation",
 "candidate_id": "CDR-20260815-001", "message": "需确认：审批门/资源门..."}
```

`action_audit` 可能值：`pass`（六道闸门全过，可建飞书任务）、`block`、`needs_confirmation`、
`gate_failed`、`no_permission`、`no_task`、`unknown_candidate`、`reject`、`revise`。

这个接口有真实业务后果：`approve` 会确认复核、生成主张、必要时 supersede 旧版本、
建任务草稿并跑六道闸门审计；闸门未过如实返回 `blocked`，不乐观放行。
幂等按 `token`，重复请求返回上次结论。`open_id` 需能映射到平台用户且是该实验成员，
否则 `no_permission`。

---

## 5. POST /api/v1/task/status — 回写飞书任务状态

实现：`app/api/integration.py:84`

```json
{"candidate_id": "CDR-20260815-001", "feishu_task_guid": "ftask_xxx", "status": "success"}
```

`status` 仅接受 `pending` / `success` / `failed`；`failed` 且携带 `error` 时记一条
`task.feishu_failed` 审计事件。响应 `{"ok": true, "task_id": "T_...", "feishu_task_guid": "ftask_xxx"}`。
候选对应会议尚无任务时返回 404。

---

## Aily 接入注意

- Aily 运行在飞书云端，**无法访问 `127.0.0.1`**。需通过隧道或公网部署暴露平台，
  参见 `labmemory-platform/deploy/README.md`（含 Aily 出口 IP 段与 checklist）。
- 仓库另有一条 MCP 通道（`AILY_MCP.md`）：Aily 连 `/mcp/sse`，通过
  `labmemory_submit_transcript` 等 10 个工具交互。`/api/v1/*` 与 MCP 是两套并行接入方式，
  择一即可。
- 公网暴露前必须把 `PLATFORM_API_KEY` 从代码默认值（`dev-platform-api-key-please-rotate`）
  换成 ≥32 字节随机串，平台 `.env` 与编排器 `config/.env` 两端同步。

## 参考实现

- `labmemory-platform/scripts/mock_feishu_push.py` — 可直接运行的推送脚本
  （`python -m scripts.mock_feishu_push single`）
- `labmemory-platform/scripts/cross_side_check.py` — 4 条契约路由的跨侧连通性检查

