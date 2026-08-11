# platform-intake Specification

## Purpose
TBD - created by archiving change add-platform-intake-contract-compliance. Update Purpose after archive.
## Requirements
### Requirement: 集成接口鉴权
系统 SHALL 在 `/api/v1/*` 集成接口上校验请求方身份：接受 `Authorization: Bearer {PLATFORM_API_KEY}`（契约要求）；为兼容既有平台测试夹具，SHALL 同时接受 `X-Platform-Api-Key: {PLATFORM_API_KEY}`。两个 header 任一值等于 `settings.PLATFORM_API_KEY` 即视为通过；均缺失或不匹配 MUST 返回 `403`。

#### Scenario: 编排器用 Bearer 通过
- GIVEN 飞书编排器以 `Authorization: Bearer {PLATFORM_API_KEY}` 调用 `POST /api/v1/candidates`
- WHEN 平台校验集成接口鉴权
- THEN 系统 SHALL 通过校验并处理请求

#### Scenario: 旧夹具用 X-Platform-Api-Key 通过
- GIVEN 平台既有测试脚本以 `X-Platform-Api-Key: {PLATFORM_API_KEY}` 调用 `/api/v1/*`
- WHEN 平台校验集成接口鉴权
- THEN 系统 SHALL 通过校验（双接受，过渡兼容）

#### Scenario: 缺鉴权或 key 错误
- GIVEN 请求未携带鉴权头或 key 不匹配 `PLATFORM_API_KEY`
- WHEN 平台校验集成接口鉴权
- THEN 系统 SHALL 返回 `403` 且 MUST NOT 处理请求

### Requirement: 集成接口 base 路径前缀
系统 SHALL 把飞书编排器集成接口统一挂在 `/api/v1` 前缀下（`POST /api/v1/candidates`、`POST /api/v1/card/callback`、`POST /api/v1/task/status`、`GET /api/v1/candidates/{candidate_id}`），使编排器 `{PLATFORM_API_BASE=…/api}/v1/*` 拼接后命中正确路由。

#### Scenario: 编排器 base 含 /api 命中
- GIVEN 编排器配置 `PLATFORM_API_BASE=https://labmemory.example.com/api`
- WHEN 编排器提交候选到 `{base}/v1/candidates`
- THEN 平台 SHALL 在 `POST /api/v1/candidates` 命中并处理（而非 404）

### Requirement: 提交候选包响应
系统 SHALL 在 `POST /api/v1/candidates` 成功受理 `CandidatePackage` 后返回包含 `status`（值 `submitted`）、`results[]`（每个候选 `{candidate_id, status}`）、`review_count`（待复核数量）、`created` 的响应，使飞书编排器能读取受理状态（`pipeline_orchestrator.py` 读取 `status` 键）。`source_package_id` MUST 可回溯到已接收的 `MeetingPackage`，否则 `404`。

#### Scenario: 受理成功返回受理状态
- GIVEN 已通过 `/api/v1/meetings` 接收会议 `meet_x` 且未提交过候选
- WHEN 飞书侧提交 `CandidatePackage`（source_package_id=meet_x，含 2 个候选）
- THEN 响应 SHALL 含 `status:"submitted"`、`results` 长度 2、`created:true`、`review_count` ≥ 1

#### Scenario: 重复提交幂等
- GIVEN 同一 `(meeting_id, source_package_id)` 的候选已提交
- WHEN 飞书侧再次提交相同包
- THEN 系统 SHALL 返回 `created:false` 且 MUST NOT 重复入库

### Requirement: 卡片回调转发与分流
系统 SHALL 在 `POST /api/v1/card/callback` 接收飞书编排器转发的**嵌套**卡片回调信封 `{token, open_id, action:{value:{action_type, candidate_id}}}`，按 `action_type` 分流并返回 `{status, action_audit, candidate_id, message}`：
- `approve`：执行复核确认（生成主张 + 任务草稿）后跑六道闸门审计，返回**真实** `action_audit`（`passed` / `needs_confirmation` / `blocked`）；`status` 为 `approved`（仅当 `action_audit=passed`）或 `blocked`。
- `reject`：复核 `decision=ended`，返回 `status:"rejected"`、`action_audit:"reject"`。
- `revise`：返回 `status:"blocked"`、`action_audit:"revise"`。

系统 SHALL 按 `token` 幂等（重复 token 返回上次结论）。系统 MUST NOT 乐观返回 `action_audit=pass` 而跳过六道闸门审计。

#### Scenario: approve 通过审计放行
- GIVEN 候选 `cand_a` 关联会议已就绪，且其任务审批/资源/失败边界门均满足
- WHEN 编排器转发 `{token:t1, open_id:ou_x, action:{value:{action_type:approve, candidate_id:cand_a}}}`
- THEN 响应 SHALL 为 `status:"approved"`、`action_audit:"passed"`，且平台已生成主张与任务草稿

#### Scenario: approve 审计未过诚实阻断
- GIVEN 候选 `cand_b` 关联任务的资源门未就绪
- WHEN 编排器转发 approve 回调
- THEN 响应 SHALL 为 `status:"blocked"`（或 `approved`+`action_audit!=passed`），MUST NOT 返回 `action_audit:"passed"`

#### Scenario: reject 结束复核
- GIVEN 候选 `cand_c` 处于待复核
- WHEN 编排器转发 `{action_type:reject, candidate_id:cand_c}`
- THEN 响应 SHALL 为 `status:"rejected"`、`action_audit:"reject"`，复核 `decision=ended`

#### Scenario: 按 token 幂等
- GIVEN 同一 `token` 的回调已处理
- WHEN 编排器重发相同 token 的回调
- THEN 系统 SHALL 返回与首次相同的结论且 MUST NOT 重复执行复核/审计

### Requirement: 任务状态回写
系统 SHALL 在 `POST /api/v1/task/status` 接收 `{candidate_id, feishu_task_guid, status, error?}`（snake_case），按 `candidate_id` → 候选行 → 会议 → 最新任务定位平台 Task，写入 `feishu_task_guid`，并按 `status`（`pending` / `success` / `failed`）记录；`failed` 时 SHALL 把 `error` 记入 `AuditEvent`。响应 SHALL 含 `{ok, task_id, feishu_task_guid}`。

#### Scenario: 成功回写任务 guid
- GIVEN 候选 `cand_a` 对应任务 `T_x` 存在
- WHEN 编排器提交 `{candidate_id:cand_a, feishu_task_guid:ftask_1, status:success}`
- THEN 系统 SHALL 把 `feishu_task_guid=ftask_1` 写到 `T_x`，并返回 `{ok:true, task_id:"T_x", feishu_task_guid:"ftask_1"}`

#### Scenario: 失败回写记原因
- GIVEN 候选 `cand_a` 对应任务存在
- WHEN 编排器提交 `{candidate_id:cand_a, feishu_task_guid:"", status:failed, error:"创建超时"}`
- THEN 系统 SHALL 记 `AuditEvent`（含 error），响应 `ok:true`

### Requirement: 候选详情查询
系统 SHALL 在 `GET /api/v1/candidates/{candidate_id}` 返回**扁平**候选对象（不包装在 `data` 字段内），字段至少含 `candidate_id`、`type`、`title`、`description`、`parameters`、`evidence`、`experiment_ref`、`status`，并富化 `meeting_title`（所属会议 title）与 `source_url`（所属会议 source_url），供编排器构建飞书任务摘要。未找到候选 MUST 返回 `404`。

#### Scenario: 返回扁平富化候选
- GIVEN 候选 `cand_a` 存在于某会议 `meet_x`（title「温度评审」）
- WHEN 编排器 `GET /api/v1/candidates/cand_a`
- THEN 响应 SHALL 为扁平对象含 `candidate_id:"cand_a"` 与 `meeting_title:"温度评审"`，且不含外层 `data` 包装

#### Scenario: 候选不存在
- GIVEN 系统`不存在 candidate_id=cand_z`
- WHEN 编排器 `GET /api/v1/candidates/cand_z`
- THEN 系统 SHALL 返回 `404`

