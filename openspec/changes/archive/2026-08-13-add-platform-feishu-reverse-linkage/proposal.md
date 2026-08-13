# Proposal: 平台 → 飞书编排器反向联动（FeishuActionRequest 落地）

## Why

契约 `openspec/specs/contracts/spec.md`「FeishuActionRequest（平台 → 飞书侧）」与 `openspec/specs/feishu-actions/spec.md` 已冻结了平台主动请求飞书执行动作的方向，但**两侧均未实现**（`INTEGRATION.md §6.4` 已记录）：

1. **编排器侧无接收端点**：`webhook_server.py` 只有 `/webhook/event`、`/webhook/card`，缺契约中平台发起动作所需的接收端点（`DEPLOYMENT.md` 提到的 `/webhook/platform` 未编码）。
2. **平台侧无出站客户端**：`app/config.py:43-44` 有 `FEISHU_ORCHESTRATOR_BASE_URL` / `FEISHU_ORCHESTRATOR_MODE=mock` 配置，但**没有任何代码**组装并发送 `FeishuActionRequest`。

结果是：平台业务节点（复核待办、任务启动、知识发布、审计阻断）无法主动通知飞书侧发卡片/建任务/发文档/告警，反向链路是 mock 空转。本次把这条反向通路**从契约落到代码**，覆盖四个触发点（`send_card` / `create_task` / `publish_doc` / `notify`）。

## What Changes

- **新增** 编排器 `core/platform_action_handler.py`：校验 `FeishuActionRequest` 必填字段、按 `idempotency_key` 幂等、按 `action_type` 分派到既有适配器（`im_card_adapter` / `task_adapter` / `docs_adapter` / `base_adapter`），`create_task` 成功后回写平台 `feishu_task_guid`。
- **修改** 编排器 `core/webhook_server.py`：新增 `POST /webhook/platform` 端点；mock 模式限 localhost，real 模式校验 `Authorization: Bearer {PLATFORM_API_KEY}`。
- **新增** 平台 `app/services/feishu_client.py`：组装并 POST `FeishuActionRequest` 到 `{FEISHU_ORCHESTRATOR_BASE_URL}/webhook/platform`；`FEISHU_ORCHESTRATOR_MODE=mock` 时不真调（记录日志返回跳过）；失败不阻断主业务（fire-and-forget）。
- **修改** 平台三个业务节点（均 try/except 包裹、非阻断）：
  - `app/api/meetings.py` `receive_candidate`：新候选待复核 → 下发 `send_card`（≤3 张）。
  - `app/api/tasks.py` `start_task`：任务启动 → `create_task`；`run_audit` 阻断 → `notify`。
  - `app/api/results.py` `publish_result`：知识发布 → `publish_doc`（按 `knowledge_status` 映射文档类型）。
- **新增** `labmemory-platform/scripts/reverse_linkage_check.py`：本地起平台 + 编排器后，直打 `/webhook/platform` 与平台业务触发点，验证反向通路。
- **不修改** 契约 `contracts/`（冻结）、正向联动代码、前端、六道闸门审计逻辑。

## Impact

- 1 个新 spec 领域增量（`platform-outbound`，ADDED 7 需求）。
- 编排器改动：新 `core/platform_action_handler.py`、`core/webhook_server.py`。
- 平台改动：新 `app/services/feishu_client.py`、`app/api/meetings.py`、`app/api/tasks.py`、`app/api/results.py`。
- 新增：`labmemory-platform/scripts/reverse_linkage_check.py`。
- 反向通路在编排器 `RUN_MODE=mock` + 平台 `FEISHU_ORCHESTRATOR_MODE=real` 下即可端到端验证（无需真飞书凭证）；真飞书落地仍需真 `FEISHU_APP_ID/SECRET` + `RUN_MODE=real`（非本次范围）。
