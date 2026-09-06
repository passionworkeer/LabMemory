# LabMemory 平台 ←→ Aily 对接说明（新架构）

> **面向 Aily 集成方的入口文档**。本文件按「新 skill v1.0.8」描述的链路撰写；
> 旧版（REST `/v1/*` 路径）已被替代，机器鉴权 REST 接口的技术细节见
> [`docs/api-meetings-integration.md`](./docs/api-meetings-integration.md)（标注为备用）。
>
> **数据口径**：本仓库全部为脱敏模拟数据，不代表晶泰科技真实业务数据。

---

## 0. 全局约定

| 项 | 约定 |
|---|---|
| **接入方式** | **MCP `/mcp/sse`（推荐）**——Aily 走 `aily-mcp install-remote` 自助接入 |
| 鉴权（MCP） | `Authorization: Bearer {PLATFORM_API_KEY}` 或 URL `?token=<PLATFORM_API_KEY>` |
| 鉴权（轮询） | `POST /api/auth/login` 拿 JWT（24h 有效，每次轮询前重新登录） |
| Content-Type | `application/json`（请求/响应均 UTF-8） |
| 平台基址（生产） | `https://<your-domain.com>` |
| 健康检查 | `GET /health` |
| 工具清单 | `GET /mcp/manifest`（自检用，鉴权后返 10 个 `labmemory_*` 工具 schema） |
| 平台版本 | `labmemory-platform v2.0.0`（持续更新，见 `/health` 响应） |

**为什么推荐 MCP 路径而不是 REST `/v1/*`**：

| 维度 | MCP `/mcp/sse`（新主路径） | REST `/v1/*`（备用） |
|---|---|---|
| 接入者 | Aily（agent 模式） | 编排器服务（:8080） |
| 鉴权 | Bearer 或 `?token=` queryParam | Bearer |
| 调用模式 | Aily 后台自助，工具由 LLM 决定何时调 | 程序化：飞书事件 → HTTP POST |
| 卡片推送 | Aily 主动 `lark-cli im +messages-send --as bot`（最后一公里） | 平台 webhook → 编排器 → 飞书 |
| 状态感知 | Aily interval 轮询 `/api/control-tower` | 平台 webhook 推回 |
| 跨租户 | 群聊/邮件两条降级通道（已在 skill 实战验证） | 需编排器配对应 bot |
| 真飞书凭证依赖 | 低（轮询账号即可） | 高（FEISHU_APP_ID/SECRET、AILY_API_KEY） |

---

## 1. Aily 接入流程（新主路径）

### 1.1 一次性配置：管理员维护云文档

凭据（URL 含 token、轮询账号）**不硬编码进 skill**，改走管理员维护的飞书云文档：

> `https://larkcommunity.feishu.cn/docx/MR7Jd1Utuo8NMkxa8nbc5zprnCe`

文档已设为「组织内可阅读」。Aily 用 `lark-cli docs +fetch` 读取后取出：
- **Server 名称**：`labmemory`
- **协议**：`sse`
- **URL**：`https://<your-domain.com>/mcp/sse?token=<从文档取>`

> **为什么不在 skill 正文里直接写 URL**：skill 市场对上架技能做内容安全扫描，
> 禁止硬编码凭据。

### 1.2 用户侧：首次接入引导（新 skill 第 0 步）

新 skill `labmemory-decision-memory` 包含完整的「首次接入引导」，分发到 Aily 后对方自助完成：

1. **检查并接入 MCP**（`aily-mcp servers` → `aily-mcp tools -s <uid>` → `aily-mcp install-remote labmemory --url ...`）
2. **解析用户身份与角色**（`lark-cli contact` 读组织架构，按职位关键词映射 PI / Lead / Executor）
3. **创建「会议纪要入档」事件自动化**（`aily-cli auto create --trigger-type event --event-type vc.note.generated_v1 ...`）
4. **创建「状态轮询」interval 任务**（`aily-cli auto create --trigger-type interval --interval 1800 --active-hours "9-22" ...`）

完整步骤、instruction 模板、踩坑记录见 [`LabMemory 决策记忆/labmemory-decision-memory/SKILL.md`](./LabMemory%20%E5%86%B3%E7%AD%96%E8%AE%B0%E5%BF%86/labmemory-decision-memory/SKILL.md)。

### 1.3 接入完成后自检清单

1. `aily-mcp servers` 能看到 `labmemory`（`configStatus=installed`）
2. `aily-cli auto list --keyword 会议纪要入档LabMemory` 命中 1 条 active（trigger=event）
3. `aily-cli auto list --keyword 状态轮询` 命中 1 条 active（trigger=interval）

三项均就位 → **完整端到端链路已通**（前半段事件驱动 + 后半段轮询感知）。

---

## 2. 平台接收的 10 个 MCP 工具（Aily → 平台）

10 个工具的完整 JSON Schema 见 [`docs/aily-skill/tools-manifest.json`](./docs/aily-skill/tools-manifest.json)
（schema 仍准确，未随架构改动）。下面是速查表：

| # | 工具 | 何时调 | 关键入参 | 幂等 |
|---|---|---|---|---|
| 1 | `labmemory_submit_transcript` | 妙记/纪要产出后立即 | `meeting_id`, `segments` | × |
| 2 | `labmemory_submit_extraction` | 抽取完成 | `transcript_id`, `params`, `evidence`, `scope` | × |
| 3 | `labmemory_create_review` | 抽取后立即 | `extraction_id`, `assignee` | × |
| 4 | `labmemory_submit_verdict` | 仅当你就是复核人 | `decision_id`, `verdict`, `reviewer` | × |
| 5 | `labmemory_issue_version` | `verdict=pass` 后兜底 | `decision_id`, `params` | **√** |
| 6 | `labmemory_preflight_check` | 实验开始前 | `version_id`, `executor` | × |
| 7 | `labmemory_submit_execution` | 实验完成 | `version_id`, `actual_params`, `results` | × |
| 8 | `labmemory_update_passport` | 主张/边界变更 | `passport_id`, `claim_state` | × |
| 9 | `labmemory_publish_knowledge` | 结果稳定后 | `passport_id`, `title`, `summary` | **√** |
| 10 | `labmemory_create_reverify` | 长周期实验 | `passport_id`, `assignee`, `due_at` | × |

> **使用注意**：
> - 每个工具调用前必须确认 ID——`meeting_id` / `transcript_id` / `extraction_id` /
>   `decision_id` / `version_id` / `passport_id` 全部来自**上一步工具的返回值**，**不要凭名字猜**。
> - `evidence` 必须带 `text` 字段、`scope` 必须是对象——六道闸门会校验，缺了会被拦。
> - 身份字段（`reviewer` / `assignee` / `executor`）从飞书组织架构解析 + 用户确认得出，不要硬编码、不要留空。
> - `actual_params` 必须如实填——偏离计划时平台会把结果**冻结（frozen）**并触发偏差卡，这是设计行为不是 bug。

---

## 3. 平台 → 飞书的 5 类事件（Aily 主动发卡）

平台内部会触发 5 类事件，但**飞书卡片到人**的"最后一公里"由 **Aily 完成**——
调完对应工具后，按下方模板主动用 `lark-cli im +messages-send --as bot` 发交互卡片。

> 这是**新架构的关键变化**：旧版（编排器路径）依赖平台 webhook 推回；
> 新版让 Aily 主动发卡，避免 webhook 失败/重试/幂等管理的复杂度，并支持跨租户灵活路由。

| 事件 | 由哪个工具触发 | Aily 发卡对象 | 按钮跳转 |
|---|---|---|---|
| `decision.pending` | `labmemory_create_review` | PI / Lead | `/review/<meeting_id>` |
| `preflight.blocked` | `labmemory_preflight_check` | Executor + PI | `/audit` |
| `execution.deviated` | `labmemory_submit_execution`（偏差时） | PI | `/result` |
| `knowledge.ready` | `labmemory_publish_knowledge` | 团队成员 | `/tower` |
| `reverify.due` | `labmemory_create_reverify`（到期） | Assignee | `/passport` |

### 3.1 收件人解析与跨租户推送规则

按 skill 「身份与权限解析」把平台角色映射到真实飞书用户后，按其租户归属选通道：

1. **同租户负责人**（默认）：bot 直发 p2p 卡片
   ```bash
   lark-cli im +messages-send --as bot --user-id <open_id> --msg-type interactive
   ```
2. **跨租户负责人**：open_id 按租户隔离，bot 无法 DM。两条降级通道（已实测可用）：
   - **群聊通道**：`--chat-id <oc_xxx>` 往含本 bot 的项目群发卡片 + `<at email="对方邮箱">`
   - **邮件通道**：`lark-cli mail +send --to <邮箱> --body <HTML含jump_url>`
3. **对方团队自助接入**：若对方团队也装了本 skill，在其租户内闭环——最干净的方式。

### 3.2 卡片通用规范

- schema **2.0**；按钮必须放 `column_set` 里；**禁用 `action` / `note` 标签**（V2 已废弃）
- 一律 `--as bot` 发送，禁止用户身份
- 幂等：`--idempotency-key "labmemory-<事件>-<业务ID>"`，同一事件只推一次
- `multi_url` 四个端（url/pc/android/ios）填同一个链接

### 3.3 5 类卡片完整 JSON 模板

见新 SKILL.md「关键环节推送卡片」章节：
- 模板 1：`decision.pending` 复核提醒卡
- 模板 2：`preflight.blocked` 审计阻断卡
- 模板 3：`execution.deviated` 执行偏差卡
- 模板 4：`knowledge.ready` 知识发布卡
- 模板 5：`reverify.due` 复验提醒卡

---

## 4. 状态轮询（后半段链路感知）

### 4.1 为什么需要轮询

前半段链路（纪要→入档→发复核卡）是事件驱动的。
后半段（PI 在平台网页点通过/驳回、执行人解决阻断、提交执行结果）发生在**平台侧**，
Aily 感知不到——MCP 工具全是写入类、没有查询类。所以需要一个 interval 定时任务
轮询平台 HTTP API，发现状态变化后继续后续步骤并发通知。

### 4.2 平台侧查询接口（轮询账号鉴权）

**注意**：MCP token 与前端 session JWT 是两套鉴权——MCP token 只能调 MCP 工具（写入类）；
平台 REST API（查询类）需走 `POST /api/auth/login` 拿 JWT（24h 有效）。

```bash
# 1. 登录拿 JWT
JWT=$(curl -s -X POST https://<your-domain.com>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<从云文档读>","password":"<从云文档读>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. 待关注事项仪表盘
curl -s -H "Authorization: Bearer $JWT" https://<your-domain.com>/api/control-tower

# 3. 会议列表（含 review 状态）
curl -s -H "Authorization: Bearer $JWT" "https://<your-domain.com>/api/meetings?experiment_id=<EXP-xxx>"
```

### 4.3 状态差异处理

| 变化 | 含义 | 后续动作 |
|---|---|---|
| `review.pending → processed(confirmed)` | PI 在平台点了「通过」 | 调 `labmemory_issue_version(decision_id)` 签发版本 → 通知用户 |
| `review.pending → processed(rejected)` | PI 在平台点了「驳回」 | 通知用户「复核被驳回，决策项已终止」 |
| `blocked_task` 从 `need_attention` 消失 | 阻断已解决 | 调 `labmemory_preflight_check(version_id)` 重新自检 |
| `need_attention` 出现新 anomaly | 新异常 | 按异常类型发对应卡片 |

完整流程、状态文件格式、踩坑记录见新 SKILL.md「状态轮询」章节。

---

## 5. 平台 webhook 协议（备用——平台能力仍在，新架构不依赖）

> **新架构下不依赖平台 webhook**（Aily 主动发卡替代），但平台的 5 类事件 webhook
> 实现仍在，保留作为「备用通道」供未来扩展（例如平台侧主动通知外部 BI、监控告警系统等）。

5 类事件（`decision.pending` / `preflight.blocked` / `execution.deviated` /
`knowledge.ready` / `reverify.due`）的 payload 字段、签名头、去重协议见
[`docs/aily-skill/webhook-payload.md`](./docs/aily-skill/webhook-payload.md)。

签名校验：
```python
import hmac, hashlib
expected = hmac.new(WEBHOOK_SECRET, raw_body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, request.headers["X-LabMemory-Signature"]):
    return 401
```

平台侧默认 `AILY_INTEGRATION_ENABLED=false`（不真推）；启用需设环境变量。

---

## 6. 工具调用规则（红线，违反会被平台拒绝）

- **每个工具调用前先确认 ID**：缺 ID 直接报错，**不要凭名字猜**。
- **返回值精简**：所有工具返回 ≤ 2 万字（不含逐字稿全文）；
  看到 `jump_url` 就嵌入飞书卡片。
- **业务异常透传**：工具返回 `isError=true` 时，把 `code` + `message` 原样转给用户，
  不要自行"修复"或猜下一步。
- **严格串行**：第 1→2→3 步必须按序；第 6 步依赖第 5 步的 `version_id`。
- **身份字段填实参**：`reviewer` / `assignee` / `executor` 从飞书会话上下文取真实用户名填入；
  不要留空（留空会被回退到 PI，污染审计归属）。

---

## 7. 失败兜底

- MCP 工具完全不可用：先按新 skill 第 0.1 步的内置配置重新接入，验证仍失败告知用户。
- 网络超时：重试 1 次；`labmemory_issue_version` 和 `labmemory_publish_knowledge` 可放心重试（幂等）。
- 平台 5xx：不无限重试，告知用户"平台侧故障，已记录"。
- 平台 4xx 业务异常：按 `code` 分类（`not_found` / `state_transition` / `gate_blocked`），把建议动作转给用户。
- 跨租户推送：群聊 / 邮件两条通道均已实测可用；若对方邮箱未知且无共建群，
  如实告知当前用户"无法触达 <角色>"。

---

## 8. 关联文档

| 文件 | 用途 |
|---|---|
| [`LabMemory 决策记忆/labmemory-decision-memory/SKILL.md`](./LabMemory%20%E5%86%B3%E7%AD%96%E8%AE%B0%E5%BF%86/labmemory-decision-memory/SKILL.md) | **新 skill 包（v1.0.8）**：接入引导 + 10 步闭环 + 5 类卡片 + 状态轮询 + 16 条踩坑 |
| [`AILY_MCP.md`](./AILY_MCP.md) | MCP 协议层细节：SSE、鉴权兼容、`/mcp/manifest` |
| [`docs/aily-skill/tools-manifest.json`](./docs/aily-skill/tools-manifest.json) | 10 个 MCP 工具完整 JSON Schema（平台 API 自检用） |
| [`docs/aily-skill/webhook-payload.md`](./docs/aily-skill/webhook-payload.md) | 平台→飞书 5 类 webhook 事件 payload（备用通道） |
| [`docs/api-meetings-integration.md`](./docs/api-meetings-integration.md) | 机器鉴权 REST `/api/v1/*` 接口技术细节（备用） |
| [`docs/platform-intake-api.md`](./docs/platform-intake-api.md) | 平台 intake 接口完整字段定义 |
| [`AUDIT.md`](./AUDIT.md) | 对抗审查与卖点实现度 |
| [`PROJECT_GUIDE.md`](./PROJECT_GUIDE.md) | 项目当前态：能力、链路、使用 |
