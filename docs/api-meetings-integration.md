# LabMemory 平台接口文档 — meetings / integration（服务器实测版）

> 基于生产服务器 `https://<your-domain.com>`（阿里云 <SERVER_IP>，2026-08-15）逐端点实测编写。
> 所有端点 **已确认开放**，鉴权、状态码、响应结构均为实测结果。
>
> 源码位置：`labmemory-platform/app/api/meetings.py`、`labmemory-platform/app/api/integration.py`

## 鉴权方式

| 接口组 | 鉴权 | 凭证 |
|---|---|---|
| `/api/v1/*`（飞书编排器契约） | 机器鉴权 | `Authorization: Bearer <PLATFORM_API_KEY>` 或 `X-Platform-Api-Key: <PLATFORM_API_KEY>` |
| `/api/meetings/*`（平台前端） | 用户 JWT | `Authorization: Bearer <access_token>`（由 `POST /api/auth/login` 获取） |

- 缺/错凭证 → **403** `{"code":"permission_denied", ...}`
- `PLATFORM_API_KEY` 在服务器 `~/labmemory/labmemory-platform/.env`，48 位强随机值
- 演示账号：pi / lead / executor / admin（密码 123456）；同一 (用户名, IP) 连续 5 次错密码锁 15 分钟（429）

---

## 一、`meetings.py` — 飞书侧推送（2 个）

### 1. `POST /api/v1/meetings` — 接收妙记会议包 ✅ 已开放

feishu-orchestrator 把 `MeetingPackage`（妙记逐字稿/纪要）推入平台，自动创建 pending 复核记录。

**请求体**（全部必填，幂等重放也须完整字段）：

```json
{
  "meeting_id": "DOC-PROBE-M001",
  "title": "实验周会",
  "source": "minutes",
  "source_object_id": "obj-m001",
  "source_url": "https://xxx.feishu.cn/minutes/m001",
  "organizer": "ou_pi_demo",
  "participants": ["ou_pi_demo", "ou_lead_demo"],
  "captured_at": "2026-08-15T09:00:00+00:00",
  "content": {
    "summary": "会议决定降温到 70 度",
    "transcript": [{"speaker": "张三", "start": 0, "end": 10, "text": "温度降到70度"}]
  },
  "metadata": {"experiment_id": "EXP-DEMO-001"}
}
```

- `metadata.experiment_id` **必填**且实验须已存在，否则 404 `not_found`

**响应 200**：`{"meeting_id": "DOC-PROBE-M001", "id": 20, "created": true}`
**幂等**：相同 `meeting_id` 再推 → `created: false` + 原 id，不重复建
**错误**：403 缺 KEY；404 实验不存在；422 字段缺失

### 2. `POST /api/v1/candidates` — 接收 Aily 抽取候选包 ✅ 已开放

把 `CandidatePackage`（参数候选/风险/行动项）挂到已接收的会议下，触发飞书复核卡片（≤3 张，fire-and-forget）。

**请求体**：

```json
{
  "source_package_id": "DOC-PROBE-M001",
  "aily_skill_version": "v1.0",
  "compiled_at": "2026-08-15T09:05:00+00:00",
  "candidates": [{
    "candidate_id": "CDR-doc-probe-1",
    "type": "parameter_change",
    "title": "温度参数变更为70度",
    "description": "会议决定降温",
    "experiment_ref": "EXP-DEMO-001",
    "parameters": [{"name": "temperature", "value": "70", "unit": "℃"}],
    "evidence": [{"text": "温度降到70度", "speaker": "张三", "start": 0, "end": 10}],
    "confidence": 0.9,
    "status": "pending",
    "needs_review": true
  }],
  "risks": [{"desc": "降温过快析出", "severity": "medium"}],
  "action_items": [{"title": "验证实验", "executor": "executor"}],
  "open_questions": []
}
```

- `source_package_id` 必须引用**已接收**的 `meeting_id`，否则 404

**响应 200**（实测）：

```json
{"id": 17, "created": true, "status": "submitted",
 "results": [{"candidate_id": "CDR-doc-probe-1", "status": "pending_review"}],
 "review_count": 5}
```

---

## 二、`meetings.py` — 平台前端复核（4 个）

### 3. `GET /api/meetings` — 复核会议列表 ✅ 已开放

**JWT**。可选 `?status=pending|processed` 过滤。按用户可见实验过滤（权限收敛）。

**实测**：全量 200（44.6KB），`?status=pending` 200（4.5KB）。
**响应**：`MeetingChainItem[]`，每项含 `meeting_id / experiment_id / title / review / claim / task / audit / results / candidates / transcript / summary` 全链路。

### 4. `GET /api/meetings/{meeting_id}` — 会议详情 ✅ 已开放

**JWT** + 须为该实验成员。比列表多 `source / source_url / organizer / participants / risks / action_items / open_questions`。
**实测**：200（1.2KB）；不存在 → 404 `not_found`。

### 5. `GET /api/meetings/{meeting_id}/chain` — 会议证据链 ✅ 已开放

**JWT** + 实验成员。返回该会议的 `review → claim → task → audit → results` 链（`MeetingChainItem`）。
**实测**：200（881B）。

### 6. `POST /api/meetings/{meeting_id}/review` — 复核确认 ✅ 已开放

**JWT** + 实验成员。人在环的决策闸门：确认/驳回候选，触发六道闸门 + 冲突检测 → 生成主张（Claim）与任务草稿（Task）。

**请求体**：

```json
{
  "decision": "confirmed" | "ended",
  "modifications": {"parameters": [...], "scope": {...}, "title": "..."},  // 可选覆盖
  "notes": "复核意见",
  "reason": "理由"
}
```

**行为**：
- `decision=ended` → 直接结束，不产生数据
- `decision=confirmed` → 六道闸门 + 高危冲突检测决定 `publish_status`：
  - `current` → 建主张 + 任务草稿（T_ 前缀），同名参数自动升版（v1→v2，值不变则继承）
  - `pending_supplement` → 建主张但不建任务（闸门/冲突拦截）
- 并发串行化：同会议并发确认，第二个请求被实验写锁拒绝
- **实测**：重复处理 → 409 `StateTransitionError`（状态机拦截正常）

---

## 三、`integration.py` — 编排器契约（3 个）

### 7. `GET /api/v1/candidates/{candidate_id}` — 候选详情 ✅ 已开放

**PLATFORM_API_KEY**。扁平对象 + 富化 `meeting_title / source_url`，供编排器构建飞书任务摘要。
demo 规模全表扫候选 JSON 匹配（生产规模可加索引列，另起 change）。

**实测响应 200**：

```json
{
  "candidate_id": "CDR-doc-probe-1", "type": "parameter_change",
  "title": "温度参数变更为70度", "parameters": [{"name": "temperature", "value": "70", "unit": "℃"}],
  "evidence": [...], "confidence": 0.9, "status": "pending", "needs_review": true,
  "assignee": null, "due_date": null,
  "meeting_title": "接口文档探测会议", "source_url": "https://example.feishu.cn/minutes/m001"
}
```

不存在 → 404 `not_found`。

### 8. `POST /api/v1/task/status` — 回写飞书任务状态 ✅ 已开放

**PLATFORM_API_KEY**。编排器把飞书任务创建结果回写平台：candidate_id → 会议最新任务。

**请求体**（`feishu_task_guid` 必填）：

```json
{"candidate_id": "CDR-doc-probe-1", "status": "pending | success | failed", "feishu_task_guid": "ftask-xxx", "error": "失败原因（status=failed 时可选）"}
```

- `status=failed` + `error` → 写 `task.feishu_failed` 审计事件
- **实测**：候选对应会议无任务时 → 404 `not_found`（业务正确：rejected 会议不建任务）
- 注意：status 只接受 `pending/success/failed` 三值，其他值 422

### 9. `POST /api/v1/card/callback` — 飞书卡片回调 ✅ 已开放

**PLATFORM_API_KEY**。转发飞书卡片按钮回调，按 `action_type` 分流。**token 级幂等**：同 token 重放返回上次结论。

**请求体**（嵌套飞书信封）：

```json
{
  "token": "callback-token-xxx",
  "open_id": "ou_xxx 或 null",
  "action": {"value": {"action_type": "approve | reject | revise", "candidate_id": "CDR-xxx"}}
}
```

**分流逻辑（实测验证）**：

| action_type | 行为 | 实测响应 |
|---|---|---|
| `reject` | 会议复核置 ended，不入数据链路 | `{"status":"rejected","action_audit":"reject"}` 200 |
| `revise` | 卡片不带修改内容，引导去前端 | `{"status":"blocked","action_audit":"revise"}` 200 |
| `approve` | 成员校验 → 六道闸门 → 建主张/任务 → 行动前审计 | passed → `{"status":"approved","action_audit":"pass"}`；闸门拦 → `{"status":"blocked","action_audit":"gate_failed"|"block"}` |
| 未知候选 | — | `{"status":"blocked","action_audit":"unknown_candidate"}` 200 |

**安全细节**：
- `open_id` 经 `User.feishu_user_id` 映射到平台用户；无映射不充当 admin
- approve 需为该**实验成员**，非成员 → `{"status":"blocked","action_audit":"no_permission"}`
- 审计结论取真实六道闸门（passed→"pass"），不乐观放行

---

## 附：实测记录摘要（2026-08-15，<your-domain.com>）

| 端点 | 无鉴权 | 带凭证 | 业务校验 |
|---|---|---|---|
| POST /api/v1/meetings | 403 | 200 created=true / 幂等 created=false | 404 实验不存在；422 缺字段 |
| POST /api/v1/candidates | 403 | 200 status=submitted | 404 会议未接收 |
| GET /api/meetings | 403 | 200 | ?status 过滤 OK |
| GET /api/meetings/{id} | 403 | 200 | 404 不存在 |
| GET /api/meetings/{id}/chain | 403 | 200 | 404 不存在 |
| POST /api/meetings/{id}/review | 403 | 200 / 409 已处理 | 状态机拦截 OK |
| GET /api/v1/candidates/{id} | 403 | 200 | 404 不存在 |
| POST /api/v1/task/status | 403 | 200 / 404 无任务 | 422 非法 status |
| POST /api/v1/card/callback | 403 | 200（三分支全验） | token 幂等重放 OK |

**公网（https://<your-domain.com>）与内网（127.0.0.1:8081）行为一致**，nginx 反代正常，`/api/v1/*` 不在 MCP SSE 特殊配置内、走 60s 常规超时。
