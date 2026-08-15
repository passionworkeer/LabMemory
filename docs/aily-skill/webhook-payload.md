# 平台 → 飞书 Webhook 推送规范

> 当 Aily 调完 MCP 工具后，平台侧会把"需要飞书侧响应"的事件通过 HMAC-SHA256 签名
> 的 HTTPS POST 推回给飞书/业务方。每个事件含 `event`、`data`、`idempotency_key` 三个字段，
> 飞书侧必须按 `idempotency_key` 做去重（同一 key 重复推是平台侧重试）。

## 通用 Headers

| 头 | 含义 |
|---|---|
| `X-LabMemory-Signature` | HMAC-SHA256(secret, raw_body)，hex |
| `X-LabMemory-Event` | 事件名（与 payload `event` 字段一致） |
| `X-LabMemory-Idempotency-Key` | 同 payload `idempotency_key` |
| `X-LabMemory-Timestamp` | 平台发送时刻（unix 秒） |

## 事件清单

### decision.pending
Aily 提交抽取完成、平台创建复核项后触发；推给飞书卡片给 PI/Lead 复核。

```json
{
  "event": "decision.pending",
  "data": {
    "decision_id": "DEC-2026-08-15-abc123",
    "transcript_id": "MTG-x9k2",
    "extraction_id": "EXT-2026-08-15-xyz",
    "assignee": "alice",
    "jump_url": "https://labmemory.example.com/review/MTG-x9k2"
  },
  "idempotency_key": "decision.pending:DEC-2026-08-15-abc123"
}
```

### preflight.blocked
实验执行前自检未通过（六道闸门任一未通过）时触发；推给飞书任务卡片给执行人 + PI。

```json
{
  "event": "preflight.blocked",
  "data": {
    "preflight_id": "PRE-...",
    "version_id": "CLM-...",
    "reasons": [
      "task.approval_status != approved",
      "task.failure_boundary_ack == false"
    ],
    "executor": "bob",
    "jump_url": "https://labmemory.example.com/audit/T-..."
  },
  "idempotency_key": "preflight.blocked:T-..."
}
```

### execution.deviated
实验执行结果回写时，actual_params 超出 planned_keys 集合；记 frozen 并触发。

```json
{
  "event": "execution.deviated",
  "data": {
    "execution_id": "R-...",
    "version_id": "CLM-...",
    "diff": {
      "planned_keys": ["temperature", "rpm", "duration"],
      "actual_keys": ["temperature", "rpm", "duration", "extra_oxygen"]
    }
  },
  "idempotency_key": "execution.deviated:R-..."
}
```

### knowledge.ready
知识发布成功后触发；推给飞书知识库 + 复验提醒。

```json
{
  "event": "knowledge.ready",
  "data": {
    "knowledge_id": "R-...",
    "passport_id": "EXP-...",
    "jump_url": "https://labmemory.example.com/result/T-..."
  },
  "idempotency_key": "knowledge.ready:R-..."
}
```

### reverify.due
复验任务到达 due_at 时由调度器触发；推给飞书任务卡片给 assignee。

```json
{
  "event": "reverify.due",
  "data": {
    "reverify_id": "RV-...",
    "passport_id": "EXP-...",
    "assignee": "carol",
    "due_at": "2026-09-15T10:00:00Z"
  },
  "idempotency_key": "reverify.due:RV-..."
}
```

## 飞书侧去重 / 重试

- 5xx 网络错误：平台最多重试 5 次（指数退避），`idempotency_key` 不变；
- 飞书侧 200 OK 但 body 含 `{"ok": false}`：平台按 5xx 处理继续重试；
- 飞书侧返回 `{"ok": true, "duplicate": true}`：平台记录后停止重试；
- 同一 `idempotency_key` 飞书侧已成功处理，再次收到应**直接返回 200 + duplicate=true**。

## 签名校验（飞书侧必做）

```python
import hmac, hashlib
expected = hmac.new(WEBHOOK_SECRET, raw_body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, request.headers["X-LabMemory-Signature"]):
    return 401
```

## 接入示例（飞书侧 webhook handler 伪代码）

```python
@app.post("/webhook/labmemory")
async def on_event(req: Request):
    raw = await req.body()
    if not verify_hmac(raw, req.headers["X-LabMemory-Signature"]):
        raise HTTPException(401)
    payload = json.loads(raw)
    event = payload["event"]
    if event == "decision.pending":
        await feishu_card_to_user(payload["data"]["assignee"], card=build_decision_card(payload))
    elif event == "preflight.blocked":
        await feishu_task_comment(payload["data"]["executor"], text=format_reasons(payload["data"]["reasons"]))
    # ...
    return {"ok": True}
```

---

> 该文档由平台 webhook 触发链路配套使用；触发位置见 `AILY_MCP.md` 第 6 节"Webhook 触发链路"。