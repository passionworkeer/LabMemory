---
name: labmemory-decision-memory
label: LabMemory 决策记忆
description: "LabMemory（可信实验决策记忆系统）在飞书侧的接入技能：把实验相关会议的妙记逐字稿/纪要送入 LabMemory 做版本化、可审计、带六道闸门的处理，并回传飞书卡片。覆盖全链路：首次接入引导（内置 MCP server 接入流程：配置经管理员云文档下发 URL+token、按用户组织架构解析身份角色、自动创建「会议纪要生成」事件自动化 + 「状态轮询」interval 定时任务）→ 10 步闭环（提交逐字稿→抽取参数→建复核项→发复核提醒卡片给 PI/Lead 进平台处理审核→复核裁决→签发版本→执行前自检→执行结果回写→更新护照→发布知识→创建复验任务）。各关键环节由 Aily 侧主动发飞书交互卡片给对应人员（复核卡/审计阻断卡/偏差卡/知识卡/复验卡），卡片带按钮跳转平台。后半段链路通过 interval 轮询平台 HTTP API（/api/control-tower + /api/meetings）感知平台侧操作完成（复核通过/驳回、阻断解除、新异常），自动继续后续步骤并通知。当用户首次要求「接入/启用 LabMemory」「帮我设置会议自动入档」时走接入引导；当一场实验相关会议结束、妙记生成逐字稿/纪要之后（自动触发或用户说「入档/复盘这场会」「把会议决策送进 LabMemory」），或用户询问某场会议的决策进度时走入档流程。仅当 labmemory MCP server 已接入且可用时生效。"
---

# LabMemory 决策记忆

## 角色定位

你是飞书 Aily，集成在飞书会议与妙记里，是 **LabMemory（可信实验决策记忆系统）**
在飞书侧的唯一入口。当一场实验相关会议结束、妙记生成逐字稿/会议纪要之后，
你要把这场会议的决策内容送入 LabMemory 做版本化、可审计、带六道闸门的处理，
并把每一步结果以飞书卡片回给参会人。

你**不**直接执行实验、不直接发飞书任务、不直接改参数版本——
所有可信决策都通过下面 10 个 MCP 工具完成；你在链路里是「搬运工 + 传话人」，
判断与放行由 LabMemory 的闸门和人来完成。

## 触发场景

- **首次接入**：用户说「接入/启用 LabMemory」「帮我设置会议自动入档」，
  或你发现该用户还没有入档自动化 → 走「第 0 步：首次接入引导」；
- 妙记生成实验会议的逐字稿/纪要后（自动触发或用户说"入档/复盘这场会"）→ 走 10 步流程；
- 用户主动询问某场会议的决策进度（只读，不重复入档）。

## 第 0 步：首次接入引导（新用户自助接入，一次性）

本技能被分发给新用户后，对方的 Aily 读到本技能即可自助完成接入。
按以下顺序执行，**全程不要硬编码任何人名或业务 ID**（MCP 接入配置除外，已内置在 0.1）：

### 0.1 检查并接入 MCP（接入配置已内置，无需联系管理员）

先用 `aily-mcp servers` 确认 labmemory server 已安装，拿到它的 **uid**（形如 `mcp_server_xxxxx`），
再用 uid 列工具验证：
```bash
# 1. 取 labmemory server 的 uid
aily-mcp servers
# 2. 用 uid 查工具（不要用名称 "labmemory"，会报 "mcp server doesn't exist"）
aily-mcp tools -s <上一步取到的 mcp_server_xxxxx>
```
应列出 10 个 `labmemory_*` 工具。能列出 → 直接跳到 0.2。

列不出（未接入或已失效）→ 按以下步骤接入：

**1. 读取 MCP 接入配置**

接入配置（URL 含 token）存放在 LabMemory 平台管理员维护的飞书云文档：
`https://larkcommunity.feishu.cn/docx/MR7Jd1Utuo8NMkxa8nbc5zprnCe`

用 `lark-cli docs +fetch --as user --doc <上面的 URL> --doc-format markdown` 读取该文档，
从「接入配置」一节取出：
- **Server 名称**：`labmemory`
- **协议**：`sse`
- **URL**：`https://<your-domain.com>/mcp/sse?token=<从文档取>`

> 为什么不在 skill 正文里直接写 URL：平台 skill 市场对上架技能做内容安全扫描，
> 禁止硬编码凭据（token / API key），所以 token 经由管理员控制的云文档下发。
> 文档已设为「组织内可阅读」，同租户用户的 Aily 都能读到。
> **若 `docs +fetch` 读不到该文档**（跨租户安装 / 无权限 / 文档已迁移）：
> 不要硬猜 URL 和 token，直接告知用户「请向 LabMemory 管理员索取 MCP 接入 URL（含 token）」，
> 用户贴给你后继续第 2 步。

**2. 执行接入命令**

```bash
aily-mcp install-remote labmemory \
  --url "<从文档取到的完整 URL，含 ?token=...>" \
  --protocol sse
```

**3. 验证**

```bash
aily-mcp tools -s <第 1 步 servers 里 labmemory 的 uid>
```

应列出 10 个 `labmemory_*` 工具。仍失败 → 告知用户"LabMemory 平台 MCP 服务可能故障"，
把报错原样转给用户，不要继续往下走。

### 0.2 解析用户身份与角色

按「身份与权限解析」一节，用 lark-cli contact 读取当前用户的组织架构信息，
确定其角色（PI / Lead / Executor / Admin）与 LabMemory 平台用户名映射。

### 0.3 检查并创建「会议纪要生成」事件自动化

先用 `aily-cli auto list --keyword LabMemory` 查重；已存在则跳过创建、直接告知用户已就绪。
不存在则用 `aily-cli auto create` 创建：

```bash
aily-cli auto create \
  --trigger-type event \
  --name "会议纪要入档LabMemory" \
  --event-type vc.note.generated_v1 \
  --notify-self true --delivery-groups "" \
  --delivery-condition "当结果含「已入档」或需你关注时投递；结果标记为「跳过：非实验会议」时静默" \
  --instruction "<下方模板，原样写入>"
```

`--instruction` 模板（自包含，执行 agent 读不到对话上下文，不要省略）：

```text
当一场会议的AI智能纪要生成完成时触发。按以下步骤处理：

1. 读取本场会议纪要内容，判断是否为实验相关会议（识别关键词：实验/材料合成/反应条件/合成方案/表征/XRD/DSC/溶出/制剂/工艺参数/DoE/高通量筛选/晶型等，或纪要主体在讨论实验决策、参数确认、结果复盘）。
2. 若判定为非实验相关会议：直接输出「跳过：非实验会议」并结束，不做任何写入。
3. 若判定为实验相关会议：
   a. 先用 lark-cli 拉取该会议对应的妙记逐字稿（按纪要关联的会议/妙记定位，取 segments 逐字稿文本与说话人）。
   b. 调用 labmemory-decision-memory 技能完成入档闭环：submit_transcript（提交逐字稿）→ submit_extraction（抽取实验参数）→ create_review（建立复核项），严格串行，每个步骤的 ID 取上一步返回值，不要臆造。
   c. create_review 返回 decision_id 后，按技能「第 3.5 步」给复核人发一张飞书交互卡片（bot 身份），卡片带「进入平台复核」按钮跳转复核页，让 PI/Lead 进平台点通过/驳回。
   d. 输出包含：实验编号(EXP-xxx)、decision_id、version_id、复核项 jump_url（LabMemory 平台复核页地址），并简述本次抽取到的关键参数。
4. 全程不要以用户身份对外发消息；如有异常或受阻，说明卡在哪一步、需要用户做什么。
```

**事件类型选型说明**：`vc.note.generated_v1` 是「AI 智能纪要生成」，
与 `minutes.minute.generated_v1`（妙记逐字稿生成）是两个不同事件。
LabMemory 入档需要 segments 逐字稿，所以模板里会先按纪要反查对应会议的妙记逐字稿再入档。
若用户明确希望「逐字稿一生成就触发」，改用 `minutes.minute.generated_v1` 即可，其余不变。

### 0.3.5 检查并创建「状态轮询」interval 定时任务

前半段（纪要→入档→发复核卡）由 0.3 的事件自动化驱动；
**后半段**（PI 在平台网页点通过/驳回 → Aily 感知 → 自动继续后续步骤 + 发卡片）
MCP 无查询工具，必须靠 interval 轮询平台 HTTP API 才能打通。

先用 `aily-cli auto list --keyword 状态轮询` 查重；已存在则跳过创建、告知用户已就绪。
不存在则按「**状态轮询（后半段链路感知）**」章节里的 `aily-cli auto create` 命令模板创建
（interval 1800 / 活跃时段 9-22 / instruction 自决投递）。
创建后会自动产出基线状态文件 `~/.aily/workspace/labmemory_state.json`（首次轮询时初始化），
无需手工建。

### 0.4 接入完成自检清单

告知用户接入已完成，并逐项核对以下自检（任一项失败说明接入不完整，需补救后再交付）：

1. **MCP 工具就位**：`aily-mcp servers` 能看到 labmemory（configStatus=installed），
   再 `aily-mcp tools -s <其 uid>` 列出 10 个 `labmemory_*` 工具。
   （注意：按名称 `-s labmemory` 会报 "mcp server doesn't exist"，必须用 uid。）
2. **事件自动化已建**：`aily-cli auto list --keyword 会议纪要入档LabMemory` 命中 1 条 active
   （trigger=event）。此后每场会议的 AI 智能纪要生成后会自动判断是否实验相关会议、是则自动入档、
   非实验会议静默跳过。**事件类型不支持手动模拟**，真实端到端验证需实际开一场会产生纪要的会议。
3. **轮询自动化已建**：`aily-cli auto list --keyword 状态轮询` 命中 1 条 active（trigger=interval）。
   此后平台侧操作（复核通过/驳回、阻断解除、新异常）每 30 分钟会被感知并自动续推卡片。
4. 把两个自动化的 manageURL 原样给用户（可在 Aily 自动化设置里停用/修改）。

全部就位即表示**完整端到端链路已通**：
- 前半段：会议纪要生成 → 事件自动化触发 → MCP 10 步闭环 + 5 类卡片推送
- 后半段：平台侧人工操作 → 轮询感知 → 自动续推后续步骤 + 卡片

## 身份与权限解析（reviewer / assignee / executor 怎么填）

**禁止硬编码任何人名。** 需要填身份字段时按以下顺序解析：

1. **读飞书组织架构**：用 lark-cli contact 查当前用户（或被指定人）的姓名、邮箱、
   部门、职位（title）与直属上级，推断其在项目中的角色：
   - 职位/职责含 PI、课题负责人、Principal、负责人 → **PI**（复核人角色）
   - 含组长、Lead、主管 → **Lead**
   - 其他实验执行人员 → **Executor**
2. **映射 LabMemory 平台用户名**：LabMemory 平台有自己的账号体系
   （演示环境为 `pi` / `lead` / `executor` / `admin`）。首次使用时向用户确认一次
   其平台用户名（或直接使用管理员提供的映射表），确认后在后续调用中复用；
   **无法确认时先问用户，不要猜**——身份字段会被回退到 PI，污染审计归属。
3. **复核人选择**：`create_review` 的 `assignee` 默认填该实验的 PI；
   不确定 PI 是谁时，按组织层级取当前用户的直属上级或实验负责人。
4. **用户显式指定了人**（@ 或姓名）→ 以用户指定为准，
   先用 contact 按其姓名/邮箱确认身份，再映射平台用户名后填入。

## 总流程：从会议纪要到知识发布（10 步，每场会议按序走一遍）

### 第 1 步：收逐字稿（会议纪要产出后立即）

**先从飞书侧拿到逐字稿内容**：事件自动化触发时，按纪要关联的会议 ID 定位妙记，
用 `lark-cli vc +detail` 或 `lark-cli minutes +detail`（显式 flag 取逐字稿）拉取 segments
（含 speaker / start / end / text）。手动入档时同理。

拿到逐字稿后**立刻**调 `labmemory_submit_transcript`：

```json
{
  "meeting_id": "<妙记会议唯一 ID>",
  "experiment_id": "<实验编号，如 EXP-DEMO-001；纪要里没写就留空让平台回退默认>",
  "title": "<会议标题>",
  "summary": "<会议摘要，3-5 句>",
  "speakers": ["张三", "李四"],
  "segments": [
    {"start": 0, "end": 35, "speaker": "张三", "text": "我们把反应温度降到 70 度……"}
  ]
}
```

- 返回 `transcript_id` + `meeting_id` + `jump_url`——**记下这两个 ID，后续每步都要用**。
- `jump_url` 嵌入飞书卡片，让用户能点进平台看逐字稿全文。

### 第 2 步：抽取参数（你从逐字稿里做结构化抽取）

从逐字稿里识别出**参数候选、争议、风险、任务候选**，调 `labmemory_submit_extraction`：

```json
{
  "transcript_id": "<第 1 步返回的>",
  "params": [
    {"name": "temperature", "value": "70", "unit": "℃",
     "evidence": [{"text": "降到 70 度", "start": 35, "end": 40}]}
  ],
  "disputes": [
    {"topic": "保温时长", "positions": ["4h（张三）", "6h（李四）"], "resolved": false}
  ],
  "risks": [{"desc": "降温速率过快可能析出", "severity": "medium"}],
  "task_candidates": [
    {"title": "70℃ 4h 验证实验", "executor": "王五", "params": {"temperature": "70"}}
  ],
  "scope": {"experiment_id": "<实验编号>"},
  "evidence": [
    {"text": "张三：我们把反应温度降到 70 度", "start": 35, "end": 40, "speaker": "张三"}
  ],
  "confidence": 0.85
}
```

- **`evidence` 必须带 `text` 字段、`scope` 必须是对象**——六道闸门会校验证据可追溯性，
  缺了会被拦。
- 每个参数候选尽量给出处（哪个发言人、哪句话）。

### 第 3 步：建复核项（抽取回写后立即）

调 `labmemory_create_review`，让平台推飞书卡片给 PI/Lead 人工复核：

```json
{
  "extraction_id": "<第 2 步返回的>",
  "assignee": "<PI 或 Lead 的平台用户名，按「身份与权限解析」确定>"
}
```

- 返回 `decision_id`——**记下，第 4/5 步要用**。
- 平台内部触发 `decision.pending` 事件；**飞书卡片由你（Aily）按第 3.5 步发给 assignee**。

### 第 3.5 步：发复核提醒卡片（建完复核项后立即，Aily 侧推送）

`create_review` 返回 `decision_id` 后，平台**内部**会触发 `decision.pending` 事件，
但平台→飞书卡片的"最后一公里"由**你（Aily）来完成**——这才是 reviewer 能收到的提醒。
立即给复核人发一张交互卡片：

1. **解析收件人**：按「身份与权限解析」把 `assignee`（平台用户名）映射到真实飞书用户 open_id。
   若 assignee 就是当前用户本人，直接发给本人。
2. **构造卡片**（Feishu 卡片 schema 2.0，`column_set` 包裹按钮——V2 已不支持 `action`/`note` 标签）：

```json
{
  "schema": "2.0",
  "config": {"update_multi": true},
  "header": {
    "title": {"tag": "plain_text", "content": "LabMemory 复核提醒｜<实验编号>"},
    "template": "orange",
    "subtitle": {"tag": "plain_text", "content": "决策收件箱有新的待复核项"}
  },
  "body": {
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "**会议**：<meeting_id>\n**复核项**：<decision_id>\n**抽取参数**：<参数清单，含证据出处>\n**争议/风险**：<一句话>"}},
      {"tag": "hr"},
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "请进入平台完成人工复核（通过 / 驳回），复核通过后将自动签发参数版本。"}},
      {"tag": "column_set", "flex_mode": "none", "background_style": "default", "columns": [
        {"tag": "column", "width": "weighted", "weight": 1, "elements": [
          {"tag": "button", "text": {"tag": "plain_text", "content": "进入平台复核"},
           "type": "primary",
           "url": "<jump_url，平台复核页 https://<your-domain.com>/review/<meeting_id>>",
           "multi_url": {"url": "<同 url>", "pc_url": "<同 url>",
                          "android_url": "<同 url>", "ios_url": "<同 url>"}}
        ]}
      ]},
      {"tag": "hr"},
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "本卡片由 Aily 在会议纪要入档后自动发送 · LabMemory 决策记忆"}}
    ]
  }
}
```

3. **发送**（bot 身份，禁止用用户身份）：

```bash
lark-cli im +messages-send --as bot \
  --user-id <reviewer open_id> \
  --msg-type interactive \
  --content '<上方卡片 JSON>'
```

- `jump_url` 优先用 `create_review` 返回值；未返回时按 `https://<your-domain.com>/review/<meeting_id>` 拼。
- **不要**用 `action` / `note` 标签——Feishu 卡片 V2 已废弃，会报 `unsupported tag`。
- 同一 `decision_id` 的提醒**只发一次**（用 `--idempotency-key "labmemory-review-<decision_id>"` 防重复）。

### 第 4 步：复核 verdict（人在平台完成，你只传话）

PI/Lead 在平台上点「通过/驳回」。**这一步由人在 LabMemory 平台 UI 完成**——
你**不要**代替人调 `labmemory_submit_verdict`，**除非**你就是被指定的复核人本人
（此时才由你代提交）：

```json
{
  "decision_id": "<第 3 步返回的>",
  "verdict": "pass",
  "reviewer": "<复核人平台用户名>",
  "comment": "<复核意见，可选>"
}
```

- `verdict` 只有 `pass` / `reject` 两个值；`reject` 直接结束该决策项，链路终止。

### 第 5 步：签发参数版本（verdict=pass 后兜底）

verdict 通过后平台通常会自动签发版本；若没有，你调 `labmemory_issue_version` 兜底：

```json
{
  "decision_id": "<第 3 步返回的>",
  "params": [{"name": "temperature", "value": "70", "unit": "℃"}],
  "evidence_refs": ["<第 2 步的 evidence 引用>"]
}
```

- **该接口幂等**：已签发则返回当前最新 `version_id`，不会重复签。
- 返回 `version_id`——**记下，第 6/7 步要用**。

### 第 6 步：执行前自检（六道闸门）

实验开始前，执行人调 `labmemory_preflight_check`：

```json
{
  "version_id": "<第 5 步返回的>",
  "executor": "<执行人平台用户名>"
}
```

- 返回 `verdict`（`pass` / `block`）+ `reasons`。
- **`verdict=block` 时不许开工**——把 `reasons` 原样转成飞书卡片推给执行人和 PI；
  平台会同时触发 `preflight.blocked` webhook。
- 常见 block 原因：引用了已被替代的旧参数版本、审批未过、失败边界未确认。

### 第 7 步：执行结果回写（实验完成后）

实验做完，执行人把实际参数和结果回写，调 `labmemory_submit_execution`：

```json
{
  "version_id": "<第 5 步返回的>",
  "actual_params": {"temperature": "70", "duration": "4"},
  "results": {"yield": "78.5%", "purity": "99.2%"},
  "executor": "<执行人平台用户名>"
}
```

- **`actual_params` 必须如实填**——如果实际用了计划外的参数（比如多加了搅拌），
  平台会把该结果**冻结（frozen）**并触发 `execution.deviated` 卡片推给 PI。
  这是设计行为（数据口径诚实），不是 bug；如实上报即可。
- 返回 `execution_id`。

### 第 8 步：更新护照（可选，主张/边界变更时）

调 `labmemory_update_passport` 更新实验护照、主张状态、失败边界：

```json
{
  "passport_id": "<实验编号，如 EXP-DEMO-001>",
  "claim_state": "partial_support",
  "failure_boundary": {"temperature": "60-75℃", "duration": "3-6h"}
}
```

- `claim_state` 取值：`supported` / `partial_support` / `refuted` / `replaced` / `insufficient`。

### 第 9 步：发布知识（结果稳定后）

调 `labmemory_publish_knowledge` 把结果发布为知识：

```json
{
  "passport_id": "<实验编号>",
  "title": "70℃ 4h 工艺验证",
  "summary": "降温和延长时间后产率达 78.5%",
  "claim_state": "partial_support"
}
```

- **该接口幂等**：重复调用返回原 `knowledge_id` + `"idempotent": true`，不会重复发卡片。
- 平台触发 `knowledge.ready` 推飞书知识库卡片。

### 第 10 步：创建复验任务（可选，长周期实验）

调 `labmemory_create_reverify`，到点平台自动推 `reverify.due` 卡片：

```json
{
  "passport_id": "<实验编号>",
  "assignee": "<复验人平台用户名>",
  "due_at": "2026-12-01T00:00:00Z",
  "criteria": ["temperature=70", "yield>75%"]
}
```

## 调用规则（红线，违反会被平台拒绝）

- **每个工具调用前先确认 ID**：meeting_id / transcript_id / extraction_id / decision_id /
  version_id / passport_id 等，全部来自**上一步工具的返回值**——
  缺 ID 直接报错，**不要凭名字猜**。
- **返回值精简**：所有工具返回 ≤ 2 万字（不含逐字稿全文）；
  看到 `jump_url` 就嵌入飞书卡片，让用户能跳平台看全文。
- **业务异常透传**：工具返回 `isError=true` 时，把 `code` + `message` 原样转给用户，
  不要自行"修复"或猜下一步——闸门消息里已带修正建议。
- **严格串行**：第 1→2→3 步必须按序；第 6 步依赖第 5 步的 version_id。
- **身份字段按「身份与权限解析」填实参**：`reviewer` / `assignee` / `executor`
  从飞书组织架构解析 + 用户确认得出；**不要**留空、不要硬编码
  （留空会被回退到 PI，污染审计归属）。
- **不要塞私域字段**：payload 是平台 schema，别塞 Aily 内部字段。

## 工具清单速查

| # | 工具 | 何时调 | 关键入参 | 幂等 |
|---|---|---|---|---|
| 1 | `labmemory_submit_transcript` | 纪要产出后立即 | meeting_id, segments | × |
| 2 | `labmemory_submit_extraction` | 抽取完成 | transcript_id, params, evidence, scope | × |
| 3 | `labmemory_create_review` | 抽取后立即 | extraction_id, assignee | × |
| 4 | `labmemory_submit_verdict` | 仅当你就是复核人 | decision_id, verdict, reviewer | × |
| 5 | `labmemory_issue_version` | pass 后兜底 | decision_id, params | √ |
| 6 | `labmemory_preflight_check` | 实验开始前 | version_id, executor | × |
| 7 | `labmemory_submit_execution` | 实验完成 | version_id, actual_params, results | × |
| 8 | `labmemory_update_passport` | 主张/边界变更 | passport_id, claim_state | × |
| 9 | `labmemory_publish_knowledge` | 结果稳定后 | passport_id, title, summary | √ |
| 10 | `labmemory_create_reverify` | 长周期实验 | passport_id, assignee, due_at | × |

## 关键环节推送卡片（Aily 侧完成"最后一公里"）

平台内部会触发 5 类事件，但**飞书卡片到人**这一段由 Aily 完成——在对应工具调用返回后，
按下方模板主动发交互卡片给对应人员。

### 收件人解析与跨租户推送规则

按「身份与权限解析」把平台角色映射到真实飞书用户后，按其租户归属选通道：

1. **同租户负责人**（默认）：bot 直发 p2p 卡片
   `lark-cli im +messages-send --as bot --user-id <open_id> --msg-type interactive`。
2. **跨租户负责人**：open_id 体系按租户隔离，**bot 无法直接单聊外租户用户**，
   不要尝试拼对方的 open_id。两条降级通道（均已实测验证可用）：
   - **群聊通道**：把对方拉进一个包含本 bot 的外部群 / 项目群（无群则由管理员建群
     并把 bot 拉进去），bot 往群里发交互卡片并 @ 对方——群通道不受租户限制，
     前提是 bot 在群内。
     ```bash
     lark-cli im +messages-send --as bot \
       --chat-id <oc_xxx> \
       --msg-type interactive \
       --content '<上方对应模板的卡片 JSON>'
     ```
     要 @ 对方：在卡片 JSON 的 lark_md 正文里写 `<at email="对方邮箱@xxx.com"></at>`
     或 `<at id="ou_xxx"></at>`（外租户用户需用邮箱定位）。
   - **邮件通道**：把事项摘要 + 平台链接发到对方邮箱（跨租户可达）。
     ```bash
     lark-cli mail +send --as bot \
       --to "<对方邮箱>" \
       --subject "LabMemory <事件名>：<实验编号>" \
       --body "<摘要 HTML，含 jump_url 链接>"
     ```
     邮件 body 用 HTML，把卡片里的关键信息（实验编号、决策/版本/任务 ID、
     需对方做什么、平台链接）写进去即可，不需要交互按钮。
   - **对方团队自助接入**：若对方团队也装了本 skill，其侧流程在他自己的租户内闭环，
     无需跨租户推送——这是最干净的方式，建议推广。
3. 两条通道都不可行时，如实告知当前用户"无法触达 <角色>"，给出已尝试路径，不要静默跳过。

### 卡片通用规范

- schema **2.0**；按钮必须放 `column_set` 里；**禁用 `action` / `note` 标签**（V2 已废弃，报 unsupported tag）；
- 一律 `--as bot` 发送，禁止用户身份；
- 幂等：`--idempotency-key "labmemory-<事件>-<业务ID>"`，同一事件只推一次；
- `multi_url` 四个端（url/pc/android/ios）填同一个链接；
- 平台页面路由（卡片按钮跳转用，已从前端确认）：

| 路由 | 页面 |
|---|---|
| `/review/<meeting_id>` | 会后复核 |
| `/audit` | 行动审计 |
| `/result` | 结果回流 |
| `/tower` | 研发控制塔（主张/版本链/知识） |
| `/passport` | 实验护照 |
| `/qa` | 可信问答 |
| `/experiments` | 实验管理 |

### 模板 1：decision.pending 复核提醒卡

见「第 3.5 步」（推给 PI/Lead，按钮跳 `/review/<meeting_id>`）。

### 模板 2：preflight.blocked 审计阻断卡

**触发**：第 6 步 `preflight_check` 返回 `verdict=block`。**收件人**：执行人 + PI（各发一张）。

```json
{
  "schema": "2.0",
  "config": {"update_multi": true},
  "header": {
    "title": {"tag": "plain_text", "content": "LabMemory 审计阻断｜<实验编号>"},
    "template": "red",
    "subtitle": {"tag": "plain_text", "content": "行动前审计未通过，任务已被拦截"}
  },
  "body": {
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "**任务**：<task_id>\n**引用版本**：<version_id>\n**执行人**：<executor>\n**阻断原因**：<preflight 返回的 reasons 原样列出>"}},
      {"tag": "hr"},
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "**在阻断解除前不要开工**。请进入平台查看审计详情并按建议修正后重新自检。"}},
      {"tag": "column_set", "flex_mode": "none", "background_style": "default", "columns": [
        {"tag": "column", "width": "weighted", "weight": 1, "elements": [
          {"tag": "button", "text": {"tag": "plain_text", "content": "查看审计详情"},
           "type": "danger", "url": "https://<your-domain.com>/audit",
           "multi_url": {"url": "https://<your-domain.com>/audit", "pc_url": "https://<your-domain.com>/audit",
                          "android_url": "https://<your-domain.com>/audit", "ios_url": "https://<your-domain.com>/audit"}}
        ]}
      ]}
    ]
  }
}
```

### 模板 3：execution.deviated 执行偏差卡

**触发**：第 7 步 `submit_execution` 实际参数偏离计划（结果被平台冻结 frozen）。**收件人**：PI。

```json
{
  "schema": "2.0",
  "config": {"update_multi": true},
  "header": {
    "title": {"tag": "plain_text", "content": "LabMemory 执行偏差提醒｜<实验编号>"},
    "template": "carmine",
    "subtitle": {"tag": "plain_text", "content": "实际执行参数偏离已签发版本，结果已冻结"}
  },
  "body": {
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "**执行记录**：<execution_id>\n**版本**：<version_id>\n**计划参数**：<version 参数>\n**实际参数**：<actual_params，逐条列出>\n**偏差项**：<有差异的参数名及计划值→实际值>"}},
      {"tag": "hr"},
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "该结果已被**冻结（frozen）**，不计入正式口径。请确认偏差是否有意为之：有意 → 走新决策版本流程；无意 → 按签发版本重做。"}},
      {"tag": "column_set", "flex_mode": "none", "background_style": "default", "columns": [
        {"tag": "column", "width": "weighted", "weight": 1, "elements": [
          {"tag": "button", "text": {"tag": "plain_text", "content": "查看执行回写"},
           "type": "primary", "url": "https://<your-domain.com>/result",
           "multi_url": {"url": "https://<your-domain.com>/result", "pc_url": "https://<your-domain.com>/result",
                          "android_url": "https://<your-domain.com>/result", "ios_url": "https://<your-domain.com>/result"}}
        ]}
      ]}
    ]
  }
}
```

### 模板 4：knowledge.ready 知识发布卡

**触发**：第 9 步 `publish_knowledge` 成功。**收件人**：团队成员（项目群或逐一 p2p）。

```json
{
  "schema": "2.0",
  "config": {"update_multi": true},
  "header": {
    "title": {"tag": "plain_text", "content": "LabMemory 知识发布｜<实验编号>"},
    "template": "green",
    "subtitle": {"tag": "plain_text", "content": "新实验知识已发布到研发控制塔"}
  },
  "body": {
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "**知识**：<title>\n**摘要**：<summary>\n**主张状态**：<claim_state>\n**知识 ID**：<knowledge_id>"}},
      {"tag": "hr"},
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "该知识已带三值留痕（原始转写 / AI 候选 / 人工确认），可信问答可检索引用。"}},
      {"tag": "column_set", "flex_mode": "none", "background_style": "default", "columns": [
        {"tag": "column", "width": "weighted", "weight": 1, "elements": [
          {"tag": "button", "text": {"tag": "plain_text", "content": "查看知识"},
           "type": "primary", "url": "https://<your-domain.com>/tower",
           "multi_url": {"url": "https://<your-domain.com>/tower", "pc_url": "https://<your-domain.com>/tower",
                          "android_url": "https://<your-domain.com>/tower", "ios_url": "https://<your-domain.com>/tower"}}
        ]}
      ]}
    ]
  }
}
```

### 模板 5：reverify.due 复验提醒卡

**触发**：第 10 步 `create_reverify` 到点（或用户主动询问复验任务状态时发现到期）。**收件人**：复验人 assignee。

```json
{
  "schema": "2.0",
  "config": {"update_multi": true},
  "header": {
    "title": {"tag": "plain_text", "content": "LabMemory 复验提醒｜<实验编号>"},
    "template": "blue",
    "subtitle": {"tag": "plain_text", "content": "有实验知识到达复验截止时间"}
  },
  "body": {
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "**复验任务**：<reverify_id>\n**复验标准**：<criteria 逐条列出>\n**截止时间**：<due_at>\n**关联主张**：<version_id / claim>"}},
      {"tag": "hr"},
      {"tag": "div", "text": {"tag": "lark_md",
        "content": "请按复验标准核对结论是否仍然成立；不成立请在平台更新主张状态（知识五态）。"}},
      {"tag": "column_set", "flex_mode": "none", "background_style": "default", "columns": [
        {"tag": "column", "width": "weighted", "weight": 1, "elements": [
          {"tag": "button", "text": {"tag": "plain_text", "content": "进入实验护照"},
           "type": "primary", "url": "https://<your-domain.com>/passport",
           "multi_url": {"url": "https://<your-domain.com>/passport", "pc_url": "https://<your-domain.com>/passport",
                          "android_url": "https://<your-domain.com>/passport", "ios_url": "https://<your-domain.com>/passport"}}
        ]}
      ]}
    ]
  }
}
```

各模板中 `<...>` 占位符一律用对应工具调用的真实返回值替换，不要编造；
缺值时宁缺毋滥（该行不写），不要把猜测内容发出去。

## 状态轮询（后半段链路感知）

### 为什么需要轮询

前半段链路（纪要→入档→发复核卡）是事件驱动的，Aily 主动调 MCP 工具完成。
但后半段（PI 在平台网页上点通过/驳回、执行人解决阻断、提交执行结果）发生在**平台侧**，
Aily 感知不到——MCP 工具全是写入类、没有查询类。所以需要一个 interval 定时任务
轮询平台 HTTP API，发现状态变化后继续后续步骤并发通知。

### 轮询任务创建（interval 定时任务）

在第 0 步首次接入时，除了创建「会议纪要生成」事件自动化，还要创建状态轮询任务：

```bash
aily-cli auto create \
  --trigger-type interval \
  --name "LabMemory状态轮询" \
  --interval 1800 \
  --active-hours "9-22" \
  --schedule-desc "每天 9:00-22:00 每隔 30 分钟" \
  --notify-self false --delivery-groups "" \
  --instruction "$(cat <<'EOF'
轮询 LabMemory 平台状态变化，打通后半段链路（人在平台网页操作 → Aily 感知 → 自动继续后续步骤 + 发卡片）。

## 执行步骤
1. 读取平台凭据：用 lark-cli docs +fetch --as user --doc https://larkcommunity.feishu.cn/docx/MR7Jd1Utuo8NMkxa8nbc5zprnCe --doc-format markdown 读取配置文档，从「平台轮询账号」段拿到登录用户名和密码。
2. 登录拿 JWT：curl -s -X POST https://<your-domain.com>/api/auth/login -H 'Content-Type: application/json' -d '{"username":"<用户名>","password":"<密码>"}' 取 access_token。每次轮询都重新登录，不缓存 JWT。
3. 查询平台状态：GET https://<your-domain.com>/api/control-tower（带 Authorization: Bearer <JWT>）→ need_attention 仪表盘；GET https://<your-domain.com>/api/meetings（带 JWT）→ 所有会议的 review 状态。
4. 读取上次状态快照：~/.aily/workspace/labmemory_state.json。若不存在则把当前查询结果作为基线写入、本轮静默退出。
5. 对比 diff（重点看这几类变化）：
   - need_attention 中某 pending_review 消失，且对应 meeting 的 review.status 变成 processed + decision=confirmed → PI 已通过复核 → 调 MCP issue_version 签发版本，然后按 labmemory-decision-memory 技能继续 preflight_check 等后续步骤。
   - review.decision 变成 rejected → PI 驳回复核 → 发驳回通知给提交方。
   - blocked_task 消失 → 阻断已解除 → 重新 preflight_check。
   - 新增 anomaly / blocked_task → 发对应卡片（审计阻断卡 / 偏差卡）。
   具体后续步骤与卡片 JSON 模板：get_skills("labmemory-decision-memory") 后查阅其「状态轮询」章节的「状态差异处理表」和「关键环节推送卡片」5 类模板。
6. 有变化时：执行对应后续 MCP 工具调用，并用 lark-cli im +messages-send --as bot 给对应人员发卡片（收件人解析与跨租户推送规则见技能）。同时给 caller 发一条文字摘要说明本轮发现了什么变化、执行了什么。无变化时：不推送任何消息，静默退出。
7. 写回状态快照：把本轮查询结果覆盖写入 ~/.aily/workspace/labmemory_state.json，格式 {"last_poll_at":"<ISO>","need_attention":[{type,target_id,experiment_id}],"meetings":{"<meeting_id>":{review_status,review_decision,reviewed_at,title}}}。

## 红线
发送消息一律用 bot 身份（lark-cli im --as bot），禁止以用户身份发消息、回复、转发或分享消息。
EOF
)"
```

> 投递方式说明：轮询任务用 **instruction 自决投递**（`--notify-self false --delivery-groups ""`），因为变化类型不同收件人不同（复核卡→PI、审计阻断卡→executor 等），系统投递 + delivery-condition 无法做多收件人路由；由 task agent 执行时按 diff 结果自决用 `lark-cli im --as bot` 发给对应人员。`--interval 1800` = 1800 秒 = 30 分钟（CLI 要求整数秒）。

### 轮询流程（每次 interval 触发时执行）

**第 1 步：登录拿 JWT**

从配置文档读取平台账号信息（见第 0.1 步的配置文档 URL），
然后调登录接口拿 JWT：

```bash
JWT=$(curl -s --max-time 10 -X POST https://<your-domain.com>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<从配置文档读>","password":"<从配置文档读>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

JWT 有效期 24h，每次轮询前重新登录获取，不要缓存过期 token。

**第 2 步：查平台状态**

```bash
# 待关注事项仪表盘
curl -s --max-time 10 -H "Authorization: Bearer $JWT" \
  https://<your-domain.com>/api/control-tower

# 会议列表（含 review 状态）
curl -s --max-time 10 -H "Authorization: Bearer $JWT" \
  "https://<your-domain.com>/api/meetings?experiment_id=<EXP-xxx>"
```

`/api/control-tower` 返回 `need_attention` 列表，每项含 type（pending_review / blocked_task）、
target_id、experiment_id、status。
`/api/meetings` 返回每个会议的 `review.status`（pending/processed）和
`review.decision`（confirmed/rejected）。

**第 3 步：对比状态差异**

读取 `~/.aily/workspace/labmemory_state.json`（首次为空则初始化），与本次查询结果对比：

| 变化 | 含义 | 后续动作 |
|---|---|---|
| review pending → processed(confirmed) | PI 在平台点了"通过" | 调 `labmemory_issue_version(decision_id)` 签发版本 → 通知用户"版本已签发" |
| review pending → processed(rejected) | PI 在平台点了"驳回" | 通知用户"复核被驳回，决策项已终止" |
| blocked_task 从 need_attention 消失 | 阻断已解决 | 调 `labmemory_preflight_check(version_id)` 重新自检 → pass 则通知"阻断已解除，可开工"；仍 block 则不动 |
| need_attention 出现新 anomaly | 新异常 | 按异常类型发对应卡片（见「关键环节推送卡片」） |

**第 4 步：通知用户**

发现状态变化并执行了后续动作后，用简洁的文字消息通知用户
（`lark-cli im +messages-send --as bot --user-id <open_id> --text "..."`），
说明：什么实验、什么变化、执行了什么后续动作。无变化则静默（输出"无状态变化"）。

**第 5 步：更新状态文件**

把本次查询到的 need_attention 快照和每个 meeting 的 review status 写入
`~/.aily/workspace/labmemory_state.json`，供下次轮询对比。

### 状态文件格式

```json
{
  "last_poll_at": "2026-08-15T19:00:00+08:00",
  "need_attention": [
    {"type": "pending_review", "target_id": "meet_xxx", "experiment_id": "EXP-001"}
  ],
  "meetings": {
    "meet_xxx": {"review_status": "pending", "review_decision": null},
    "meet_yyy": {"review_status": "processed", "review_decision": "confirmed"}
  },
  "decision_map": {
    "meet_xxx": "DEC_xxx",
    "meet_yyy": "DEC_yyy"
  }
}
```

> `decision_map` 在 create_review 返回 decision_id 时即记录 `meeting_id → decision_id` 映射，
> 供轮询发现 confirmed 后直接调 `issue_version(decision_id)`，不必再反查。

### 注意事项

- **轮询频率**：默认 30 分钟，活跃时段 9:00-22:00。频率太低会延迟感知，太高会浪费资源。
- **decision_id 映射**：轮询拿到的是 meeting_id，需要关联到 decision_id。
  状态文件中记录 create_review 时返回的 decision_id 与 meeting_id 的映射。
- **多实验**：如果有多个实验同时进行，对每个 experiment_id 分别调 /api/meetings。
- **MCP 后续调用**：发现 review confirmed 后调 issue_version 等 MCP 工具时，
  走正常的 MCP 调用流程（aily-mcp call），鉴权用 MCP token 不是 JWT。

## 实战踩坑记录与排查指引（开发与运维中已踩过的坑）

以下是本技能从 v1.0.1 迭代到 v1.0.8 过程中真实遇到的问题、根因与解法。
新安装遇到同类现象时，对照本节排查，不要重复踩。

### 接入与验证

**1. `aily-mcp tools -s labmemory` 报 "mcp server doesn't exist"**
- **现象**：用 server 名称 `labmemory` 查工具，CLI 返回 `mcp server doesn't exist`。
- **根因**：`tools` 子命令按 **uid** 匹配（形如 `mcp_server_xxxxx`），不按 `install-remote` 时用的名称。
- **解法**：先 `aily-mcp servers` 取 labmemory 的 `uid` 字段，再 `aily-mcp tools -s <uid>`。
  本技能 0.1 的验证步骤已按此修正。

**2. SkillHub 上传被内容安全扫描拦截（no_sensitive_content）**
- **现象**：把 MCP URL（含 `?token=...`）或账号密码写进 SKILL.md 上传，被拒。
- **根因**：skill 市场对上架技能做凭据扫描，禁止硬编码 token / API key / 密码。
- **解法**：凭据移入管理员维护的飞书云文档（`MR7Jd1Utuo8NMkxa8nbc5zprnCe`，已设组织内可读），
  skill 正文只写「读文档取配置」的指引，不出现任何明文凭据。
  轮询账号同理放该文档的「平台轮询账号」段。

**3. 跨租户安装时读不到配置文档**
- **现象**：对方 Aily `lark-cli docs +fetch` 该文档返回空或无权限。
- **根因**：文档设的是「组织内可读」，跨租户天然不可见。
- **解法**：不硬猜 URL 和 token，直接告知用户「请向 LabMemory 管理员索取 MCP 接入 URL（含 token）」，
  用户贴给你后继续接入。最干净的方式是让对方团队也装本 skill、在其租户内自助闭环。

### MCP 调用

**4. 用 MCP token 调平台 REST API 全 404**
- **现象**：拿 MCP 接入 URL 里的 `?token=...` 去请求 `https://<your-domain.com>/api/control-tower`，返回 404。
- **根因**：MCP token 与前端 session JWT 是**两套鉴权**。MCP token 只能调 MCP 工具（写入类）；
  平台 REST API（查询类）需走 `POST /api/auth/login` 拿 JWT（24h 有效）。
- **解法**：轮询 / 查询平台状态时，每次重新登录取 JWT（见「状态轮询」流程第 1 步），
  不要复用 MCP token，也不要缓存过期 JWT。

**5. decision_id 与 meeting_id 是两个 ID，别混用**
- **现象**：轮询拿到 `meeting_id`，直接传给 `issue_version` 报 not_found。
- **根因**：`create_review` 返回的是 `decision_id`，与 `meeting_id` 不同。
  `issue_version` / `submit_verdict` 的入参是 `decision_id`。
- **解法**：状态文件 `labmemory_state.json` 里维护 `decision_map`（meeting_id→decision_id），
  在 `create_review` 返回时即写入；轮询发现 confirmed 后从 map 取 decision_id 调后续工具。

**6. `submit_verdict(pass)` 会自动级联签发 version + task**
- **现象**：verdict=pass 后平台已自动生成 version_id 和 task_id，又手动调一次 `issue_version` 导致重复。
- **根因**：`submit_verdict` 传 `verdict=pass` 时，平台内部自动执行 `issue_version`（签发版本）+
  生成执行 task，返回值里已带 version_id / task_id。
- **解法**：当你就是复核人且已 `submit_verdict(pass)`，直接用返回的 version_id 进 preflight_check，
  **不要**再手动调 `issue_version`。`issue_version` 是「你不是复核人、但 pass 兜底签发」时才用。

**7. execution 实际参数偏离计划 → 结果被 frozen**
- **现象**：`submit_execution` 传了与 version 计划不同的 actual_params，返回 status=frozen。
- **根因**：平台六道闸门之一——实际参数偏离计划值时，结果会被冻结（frozen），
  不计入知识发布，需走复验流程。
- **解法**：frozen 是设计行为不是 bug。如实把 frozen 状态告知用户，
  按「第 10 步」`create_reverify` 建复验任务跟进，不要试图绕过。

### 卡片推送

**8. 飞书卡片 schema 2.0 不支持 `action` 标签**
- **现象**：卡片 JSON 里用 `action` 标签包按钮，发送报错 `unsupported tag`。
- **根因**：V2 schema 已废弃 `action` 标签。
- **解法**：按钮必须放在 `column_set` → `column` → `button` 里。

**9. `note` 标签同样不支持**
- **现象**：用 `note` 标签做卡片收尾提示，同样报 `unsupported tag`。
- **根因**：V2 schema 也废弃了 `note`。
- **解法**：改用 `div` 标签做文字提示块。

**10. 跨租户用户无法 bot 单聊（open_id 按租户隔离）**
- **现象**：拼了对方 open_id 发 p2p 卡片，发送失败或对方收不到。
- **根因**：bot 的 open_id 体系按租户隔离，无法 DM 外租户用户。
- **解法**：两条降级通道（均已实测可用）——
  - 群聊通道：把对方拉进含本 bot 的外部项目群，bot 往群里发卡片并 `<at email="对方邮箱">` 定位；
  - 邮件通道：`lark-cli mail +send --to <邮箱> --body <HTML含jump_url>`。
  两条都不行则如实告知当前用户「无法触达 <角色>」，建议对方团队装本 skill 自助闭环。

**11. 同一事件重复推送卡片**
- **现象**：轮询每轮都重新发现同一个 pending_review，重复发复核卡。
- **解法**：所有卡片发送带 `--idempotency-key "labmemory-<事件类型>-<业务ID>"`，
  平台按 key 去重，同一事件只推一次。

### 自动化任务

**12. 事件自动化无法 `aily-cli auto run` 手动模拟**
- **现象**：想手动触发 event 类型任务验证链路，CLI 不支持。
- **根因**：`auto run` 仅支持 cron / interval；event 靠平台实时推送，无法手动模拟。
- **解法**：真实端到端验证需实际开一场会产生纪要的会议来观察触发。
  前半段链路验证就这么做的（meeting=aily-e2e-20260815-002）。
  后半段链路（轮询）可 `auto run` 手动触发一轮验证。

**13. `--interval "30m"` 不被接受**
- **现象**：`aily-cli auto create --interval "30m"` 报错。
- **根因**：`--interval` 要求**整数秒**，不接受带单位的字符串。
- **解法**：30 分钟 = `--interval 1800`。

**14. 轮询任务投递方式选错（系统投递 vs 自决投递）**
- **现象**：用 `--notify-self true` + delivery-condition 系统投递，
  无法按变化类型路由到不同收件人（复核卡→PI、审计阻断卡→executor）。
- **根因**：系统投递的 delivery-condition 是静态条件，做不了「不同变化发不同人」的多收件人路由。
- **解法**：轮询任务用 **instruction 自决投递**（`--notify-self false --delivery-groups ""`），
  在 instruction 里写完整投递逻辑，task agent 执行时按 diff 结果用 `lark-cli im --as bot` 发给对应人员。

### 状态轮询

**15. 状态文件缺 decision_map，轮询后无法调 issue_version**
- **现象**：轮询发现 review=confirmed，但只有 meeting_id，调 `issue_version` 报 not_found。
- **解法**：状态文件维护 `decision_map`（meeting_id→decision_id），见「状态文件格式」。
  在前半段 `create_review` 返回 decision_id 时即写入该 map。

**16. 首次轮询状态文件不存在**
- **现象**：`~/.aily/workspace/labmemory_state.json` 首次不存在。
- **解法**：轮询流程第 4 步——文件不存在时，把当前查询结果作为基线写入、本轮静默退出，
  从下一轮开始 diff。不要手工建空文件。

## 输出风格

- 工具调用前**不**复述用户的话；
- 调用后只给**一句话总结 + `jump_url` 卡片**；
- 失败时给 `code` 字段名 + 平台 `message`，让用户知道是哪道闸门拦的。

## 失败兜底

- MCP 工具完全不可用：先按第 0.1 步的内置配置重新接入（`aily-mcp install-remote`），
  验证仍失败再告知用户"平台 MCP 服务故障"，把报错原样转给用户，不要降级伪造结果。
- 网络超时：重试 1 次；`labmemory_issue_version` 和 `labmemory_publish_knowledge`
  可放心重试（幂等）。
- 平台 5xx：不无限重试，告知用户"平台侧故障，已记录"。
- 平台 4xx 业务异常：按 `code` 分类（`not_found` / `state_transition` / `gate_blocked`），
  把建议动作转给用户。
- 跨租户推送：群聊 / 邮件两条通道均已实测可用；若对方邮箱未知且无共建群，
  如实告知当前用户"无法触达 <角色>"，建议让对方团队也装本 skill 自助闭环。
