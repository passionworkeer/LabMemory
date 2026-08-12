# Tasks: align-lark-cli-adapters

## 1. 妙记适配器（minutes_adapter.py）

- [x] 1.1 `_real_search`：`--start-time` / `--end-time` → `--start` / `--end`，加 `--as user`
- [x] 1.2 `_real_get_detail`：`--minute-token` → `--minute-tokens`，去掉 `--user-access-token`，改用 `--as user`
- [x] 1.3 `_real_get_detail`：逐字稿改为从 `--output-dir` 落盘文件读取并解析；文件缺失时判定逐字稿缺失并抛错
- [x] 1.4 `--dry-run` 验证两条命令的请求体

## 2. 任务适配器（task_adapter.py）

- [x] 2.1 `_real_create_task`：去掉 `--tenant-access-token`，改 `--as bot`；`--followers` 对齐为可重复的 `--follower`
- [x] 2.2 `_real_get_task`：`task +get` 不存在 → 改用 `lark-cli api GET /open-apis/task/v2/tasks/{task_guid}`
- [x] 2.3 `_real_update_task_status`：`task +update --status` 不存在 → 按状态分派 `task +complete` / `task +reopen`
- [x] 2.4 `--dry-run` 验证三条路径

## 3. 卡片适配器（im_card_adapter.py）

- [x] 3.1 `_real_send_card`：`im +send-card --receive-id --card` → `im +messages-send --msg-type interactive --content`，收件人按 `ou_` / `oc_` 前缀选 `--user-id` / `--chat-id`
- [x] 3.2 `_real_update_card`：`im +update-card` → `lark-cli api PATCH /open-apis/im/v1/messages/{message_id}`
- [x] 3.3 去掉 `--tenant-access-token`，改 `--as bot`
- [x] 3.4 `--dry-run` 验证发卡与更新卡片

## 4. 多维表格适配器（base_adapter.py）

- [x] 4.1 `_real_add_record`：`+create-record --app-token --fields` → `+record-batch-create --base-token --table-id --json`（`{"create_records":[{...}]}`）
- [x] 4.2 `_real_update_record`：→ `+record-batch-update --json`（`{"update_records":{"recX":{...}}}`）
- [x] 4.3 `_real_get_record` / `_real_list_records`：→ `+record-get --record-id` / `+record-list --limit`
- [x] 4.4 `--dry-run` 验证四条命令

## 5. 文档适配器（docs_adapter.py）

- [x] 5.1 `_real_publish`：`docx +create` → `docs +create --title --content --doc-format markdown`
- [x] 5.2 `_real_get_doc` / `_real_list_docs`：→ `docs +fetch --doc` / `docs +search`
- [x] 5.3 `--dry-run` 验证

## 6. 配置清理

- [x] 6.1 `config/env.example` 与 `config/.env` 移除 `FEISHU_TENANT_ACCESS_TOKEN` / `FEISHU_USER_ACCESS_TOKEN`（对 CLI 调用无效），改为注明飞书凭据由 `lark-cli` 管理
- [x] 6.2 `core/config.py` 移除对应字段及其引用
- [x] 6.3 `DEPLOYMENT.md` 更新为 `lark-cli config bind` / `auth login` 流程

## 7. 测试与回归

- [x] 7.1 新增单测：收件人前缀 → `--user-id` / `--chat-id` 的选择逻辑
- [x] 7.2 新增单测：任务状态 → `+complete` / `+reopen` 的分派逻辑
- [x] 7.3 `python tests/test_integration.py` 与 `tests/test_phase3.py` 全绿
- [x] 7.4 `python scripts/health_check.py` 与 `scripts/demo_end_to_end.py` 无回归

## 8. 归档

- [x] 8.1 `openspec validate align-lark-cli-adapters --strict` 通过
- [x] 8.2 `openspec archive align-lark-cli-adapters --yes`

## 验证边界（必须如实告知）

`--dry-run` 只验证请求体构造正确，**不代表真实调用成功**。真实链路验证需使用者完成 `lark-cli auth login`（读私有妙记必需 user 身份），且飞书应用需具备 `minutes:minute:read`、`task:task:write`、`im:message:send_as_bot`、`bitable:app:write`、`docx:document:write` 权限。本 change 不声称已完成真实端到端验证。
