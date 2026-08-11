# Design: 平台集成接口契约合规化

## 目标与约束

- 把 `labmemory-platform` 拉回 `openspec/specs/contracts/spec.md:56-57` 冻结契约，使真实 `feishu-orchestrator` 可直连。
- 不改契约（契约冻结，任何契约变更需另起 change + 版本升级）。
- 不破坏既有平台行为：JWT 端点、前端、e2e_test 在同步前缀/鉴权后仍全绿。
- 不依赖真飞书凭证：跨侧 e2e 用编排器同款客户端（urllib + Bearer）直打平台。

## 关键决策

### D1 鉴权：双接受 Bearer + X-Platform-Api-Key
契约要 `Authorization: Bearer`，但平台既有 e2e_test/mock_feishu_push 用 `X-Platform-Api-Key`。**双接受**避免一刀切破坏：`verify_platform_api_key(authorization, x_platform_api_key)` 从 `authorization` 去 `Bearer ` 前缀取 token，任一 header 值 == `settings.PLATFORM_API_KEY` 即通过。过渡期安全（两把钥匙同一把 dev key；生产旋转 key 时两侧同步即可）。

### D2 base 路径：v1_router 前缀 /v1 → /api/v1
编排器 `{PLATFORM_API_BASE=…/api}/v1/candidates` 期望平台服务在 `/api/v1/candidates`。把 `v1_router` 前缀改 `/api/v1`，路由变 `/api/v1/meetings`、`/api/v1/candidates`、`/api/v1/card/callback`、`/api/v1/task/status`、`/api/v1/candidates/{id}`，恰好对齐。平台前端路由 `/api/meetings` 等硬编码在 `router`（非 v1_router）上，不受影响。

### D3 保留 /api/v1/meetings 作 MeetingPackage intake
契约 4 路由不含 `POST /meetings`，但平台 e2e 依赖它注入 MeetingPackage（模拟妙记接入）。作为平台**额外** intake 保留，不与契约冲突（契约是「至少这 4 条」的最小集，平台可有多）。`source_package_id` 必须先有 meeting 才能接 candidate，这条 intake 是 candidate 提交的前置。

### D4 candidate_id → 业务对象解析：JSON 扫描（demo 规模）
`Candidate.candidates` 是 JSON 数组，`candidate_id` 埋在内部。提供 helper `_resolve_candidate(db, candidate_id) -> (Candidate_row, candidate_dict, Meeting)`：遍历 `Candidate` 行、`json` 数组匹配 `candidate_id`。demo 规模（单实验数会议）O(候选总数) 可接受；生产规模可后续加 `candidate_id` 索引列（另起 change）。任务定位（task/status）链路：candidate_id → Candidate 行 → meeting_id → 该会议最新 Task。

### D5 /api/v1/card/callback 诚实审计（不乐观 pass）
编排器仅在 `status="approved" AND action_audit="pass"` 后建飞书任务（`card_handler.py:57`）。平台既有审计是独立后置步骤（`/api/tasks/{id}/audit`）。本路由把 approve **同步折叠**为「复核确认 → 生成主张/任务草稿 → 跑六道闸门 `_run_checks`」，返回**真实** `action_audit`（passed/blocked/needs_confirmation）。这保住「行动前审计」产品价值——不在卡片层乐观放行。映射：
- `approve` → 复核 confirmed + 审计 → `{status: passed?}"approved":"blocked", action_audit: <真实结论>}`。
- `reject` → 复核 ended → `{status:"rejected", action_audit:"reject"}`。
- `revise` → `{status:"blocked", action_audit:"revise"}`（编排器 blocked 分流）。

### D6 open_id 身份映射
卡片回调只有飞书 `open_id`，无平台 JWT。`User.feishu_user_id` 列可映射；无映射时用系统占位用户（admin）执行操作、`AuditEvent.actor` 记原始 open_id。短期不做 open_id → user 全量映射（另起 change），保证审计可追溯即可。

### D7 服务层抽取（避免逻辑重复）
抽 `app/services/review.py::confirm_review_core(db, meeting, review, user, decision, modifications, notes) -> (claim, task)` 与 `app/services/audit.py::run_audit_core(db, task, user) -> ActionAudit`，从 `meetings.py:confirm_review` 与 `tasks.py:run_audit` 抽核心。JWT 端点与新 `/api/v1/card/callback` 共用，行为不变，回归测试守护。

### D8 幂等
`/api/v1/card/callback` 按 `token`（飞书信封字段）幂等：重复 token 返上次结果（查 `AuditEvent` action=`card_callback`、target_id=token）。`/api/v1/task/status` 按 `(candidate_id, feishu_task_guid)` 幂等（重复写不报错）。`/api/v1/candidates`、`/api/v1/meetings` 既有幂等保留。

## 非目标

- 不实现真飞书 webhook 验签联调（需真凭证）。
- 不做 candidate_id 索引列优化（demo 规模够用）。
- 不改前端业务（仅 dist 构建）。
- 不动 `feishu-orchestrator` 代码（已合规；其自带 `mock/mock_server.py` 的扁平字段 bug 不属于本 change 范围，平台按嵌套契约实现）。

## 风险

- **回归**：v1 前缀改动影响 e2e_test/mock_feishu_push → 同步改夹具 + 重跑。
- **审计折叠语义**：approve 同步跑审计可能因资源/失败边界未就绪而返 needs_confirmation/blocked——这是**诚实**行为，cross_side_check 断言结构合法即可，不强求 pass。
- **Python 3.11**：平台源码 3.11 可跑（A 计划已验证）；新代码沿用 `from __future__ import annotations` + snake_case Pydantic。
