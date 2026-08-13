# Design: 平台 → 飞书编排器反向联动

## 目标与约束

- 把 `FeishuActionRequest` 反向通路从契约落到代码，覆盖 `send_card` / `create_task` / `publish_doc` / `notify` 四个触发点（`update_base` 也分派，但平台暂不触发）。
- 不改契约（`contracts/feishu-action-request.schema.json` 冻结，必填字段 `schema_version`/`action_id`/`action_type`/`idempotency_key`/`actor_user_id`/`payload`）。
- 不破坏正向联动与平台主业务：出站调用一律 fire-and-forget，失败/超时只记日志。
- 无需真飞书凭证即可验证：编排器 `RUN_MODE=mock` 时适配器返回生成 ID，通路照常走 HTTP。

## 关键决策

### D1 端点与鉴权：`POST /webhook/platform` + 共享 key
编排器 `webhook_server.py` 新增 `/webhook/platform`。鉴权策略沿用既有 `/webhook/event`、`/webhook/card` 的模式：
- mock 模式：仅允许 localhost（防未设 `RUN_MODE=real` 暴露）。
- real 模式：校验 `Authorization: Bearer {PLATFORM_API_KEY}`（复用编排器与平台共享的 `PLATFORM_API_KEY`，对称共享密钥）。

### D2 幂等：`platform_action:{idempotency_key}`
复用 `IdempotencyGuard` 三步：`check`（已处理返缓存）→ `acquire`（O_EXCL 占位，防并发）→ 成功后 `mark` / 失败 `release`。`idempotency_key` 由平台按业务事件确定性生成（如 `publish_doc:{result_id}`），重发不重复执行。

### D3 分派复用既有适配器
不新增飞书调用能力，`PlatformActionHandler._dispatch` 直接映射：
- `send_card` → `im_card_adapter.send_review_card(receive_id, candidate, meeting_title, source_url)`
- `create_task` → `task_adapter.create_from_candidate(candidate, meeting_title, source_url)`，成功后 `platform_client.update_task_status(candidate_id, task_guid, "success")` 回写
- `publish_doc` → `docs_adapter.publish_knowledge(candidate, meeting_title, doc_type)`
- `notify` → `im_card_adapter.send_alert_card(receive_id, title, reason, retry_action)`
- `update_base` → `base_adapter.batch_add_records(candidates, meeting_title)`

### D4 平台出站客户端 `feishu_client.py`
`send_feishu_action(action_type, actor_user_id, candidate_id, payload, idempotency_key)` 组装契约体后：
- `FEISHU_ORCHESTRATOR_MODE != "real"`：记日志返回 `{status:"skipped"}`，不真调。
- `real`：`urllib` POST 到 `{base}/webhook/platform`，超时 10s，异常返回 `{status:"error"}` 不抛。

`actor_user_id` 取 `user.feishu_user_id or user.username`（飞书 open_id 映射未全量，与 `platform-intake` D6 一致，mock 通路不受影响）。

### D5 四个触发点（非阻断）
1. **复核待办 → send_card**：`meetings.py:receive_candidate` 提交候选后，对 `needs_review` 候选（≤3 张）请求发复核卡；`receive_id` 用 `meeting.organizer`（或首参会人）作最佳努力占位。
2. **任务启动 → create_task**：`tasks.py:start_task` 任务转 `running` 后请求建飞书任务；`candidate_id` 取该会议候选的 `candidate_id`。
3. **知识发布 → publish_doc**：`results.py:publish_result` 发布后请求发知识文档；`doc_type` 映射 `supported→success`、`refuted→failure`、`partially_supported→failure`（失败边界根因标「假设」由 `docs_adapter` 既有行为保证）。
4. **审计阻断 → notify**：`tasks.py:run_audit` 结论 `blocked` 时请求发告警卡；`receive_id` 用任务负责人或操作者。

每个触发点统一包 `try/except`，失败仅 `logger.warning`，不影响原接口响应。

### D6 验证脚本 `reverse_linkage_check.py`
平台侧新增脚本：起（或复用已起的）平台后，用 `urllib` + `Authorization: Bearer {PLATFORM_API_KEY}` 直打编排器 `POST /webhook/platform`，并对平台业务触发点（复核/审计阻断/任务启动/知识发布）走 JWT 全链路，断言编排器返回的 `ok`/`status` 与资源 ID 结构合法。编排器侧保持 `RUN_MODE=mock`。

## 非目标

- 不实现平台用户 `feishu_user_id` 全量映射（receive_id 占位，另起 change）。
- 不改契约 schema 与 `contracts/`。
- 不改正向联动（编排器 `platform_client.py` 与平台 `/api/v1/*` 已合规）。
- 不接真飞书凭证（`FEISHU_APP_ID/SECRET`、`AILY_API_KEY`、`RUN_MODE=real` 属上线前人工验收）。

## 风险

- **双发卡片**：正向（编排器 pipeline 发卡）与反向（平台 `receive_candidate` 发卡）是两条并列路径，若同时开启会重复发卡。真实部署二选一；本次默认 `FEISHU_ORCHESTRATOR_MODE=mock`（平台不真调），仅显式 `real` 时才出站，风险可控。
- **同步端点延迟**：real 模式出站最长阻塞 10s。默认 mock 即时返回；real 为显式 opt-in。
- **回归**：触发点均为追加、try/except 包裹，不动原返回结构与状态机，平台 e2e/pytest 应保持全绿。
