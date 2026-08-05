# Proposal: 回溯补齐 feishu-orchestrator 规格

## Why

`feishu-orchestrator` 子系统已在 commit `3c91afd`（feat(flute): 新增飞书编排与 AI 接入子系统）中落地实现，但 `openspec/specs/` 中**没有任何一条规格覆盖它**。当前源真相只描述平台侧四个领域（decision-inbox / trust-rules / action-audit / result-backflow）与一份 `contracts`。这违反 CLAUDE.md 第 0 节红线第 1、6 条：飞书侧行为只活在代码与 README 里，后续任何改动都无基线可比，AI 助手也无法判断偏离。

同时，代码与已归档的 `specs/contracts/spec.md` 已经出现**三处实质性偏离**，必须显式收敛而不是静默共存：

1. **MeetingPackage 字段**：规格要求 `meeting_id` / `minute_token` / `segments[]`，实际 `contracts/meeting-package.schema.json` 用 `source_object_id` / `content.transcript[]`（`speaker` / `start_offset_sec` / `end_offset_sec` / `text`）。
2. **CandidatePackage 字段**：规格要求 `compiler_version` / `meeting_id`，实际用 `source_package_id` / `aily_skill_version`；候选项必填为 `candidate_id/type/title/confidence/evidence/status`。
3. **平台接口路径**：规格写 `POST /integration/meetings`，实际实现为 `POST /v1/candidates`、`POST /v1/card/callback`、`POST /v1/task/status`、`GET /v1/candidates/{id}`。

另有一处**安全缺口**：`core/webhook_server.py` 的 `verify_signature()` 目前是桩实现（源码内标注 TODO），事件与卡片回调未真正验签。本 change 将其写入规格并列入 tasks 修复。

## What Changes

**新增 4 个领域规格（ADDED）**，覆盖飞书编排子系统实现事实：

- `meeting-ingest`：Webhook 端点与验签、事件路由与幂等、妙记读取、MeetingPackage 组装
- `decision-compiler`：Aily 技能编译、候选包产出、Aily 只能产候选的边界
- `feishu-actions`：交互卡片下发与回调三值分流（approved/rejected/blocked）、任务创建与回写、多维表格/知识文档回流
- `orchestration-reliability`：编排状态机（9 状态）、幂等（7 天 TTL）、重试（指数退避 + 抖动）、集成日志（脱敏 JSONL）、运行模式（`RUN_MODE=mock` 默认）

**修改 1 个既有领域规格（MODIFIED）**：

- `contracts`：把 `MeetingPackage` / `CandidatePackage` / `FeishuActionRequest` / 平台接口路径三处对齐为契约 JSON Schema 的真实字段，并明确 `FeishuActionRequest` 必须补齐 `action_id` / `idempotency_key` / `actor_user_id`。

## Non-goals

- 不重写 `feishu-orchestrator` 现有实现逻辑；除验签与 `FeishuActionRequest` 必填字段外，不做行为变更。
- 不改动平台侧四个领域规格（decision-inbox / trust-rules / action-audit / result-backflow）。
- 不接入真实妙记 / 真实凭据；`RUN_MODE=mock` 仍是默认与验收路径。
- 不涉及 Phase 3 未完成项（协同看板、知识文档发布的真实模式验收）的新功能设计。

## Impact

- 受影响规格：新增 `specs/meeting-ingest/`、`specs/decision-compiler/`、`specs/feishu-actions/`、`specs/orchestration-reliability/`；修改 `specs/contracts/`。
- 受影响代码：`feishu-orchestrator/core/webhook_server.py`（验签落地）、`feishu-orchestrator/contracts/feishu-action-request.schema.json`（必填字段）。其余代码仅做规格与实现一致性核对。
- 归档后，飞书侧任何后续改动都必须先走 change，与平台侧规则一致。
