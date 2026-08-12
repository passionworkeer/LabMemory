# Proposal: 适配层对齐 lark-cli 1.0.86

## Why

`feishu-orchestrator` 的 Real 模式通过 `subprocess` 调用 `lark-cli`，但这批 `_real_*` 方法从未在真实环境执行过。本机装上官方 CLI（`@larksuite/cli` v1.0.86）后逐条比对 `--help`，发现调用契约大面积不符——Real 模式一旦开启，四条出向链路会直接失败。

已确认的不符项：

- **身份传递方式错误（4 个适配器共 8 处）**：代码追加 `--tenant-access-token`，该 flag 不存在。真实 CLI 用 `--as user|bot`，凭据存于 lark-cli 自身的系统钥匙串。这使 `config/.env` 里的 `FEISHU_TENANT_ACCESS_TOKEN` / `FEISHU_USER_ACCESS_TOKEN` 对 CLI 调用完全无效。
- **域名错误**：`docx` 域不存在，实际为 `docs`；`docx +create/+get` → `docs +create/+fetch`（`--content` + `--doc-format markdown`）。
- **多维表格命令全错**：`base +create-record/+update-record/+get-record/+list-records` 均不存在，实际为 `+record-batch-create` / `+record-batch-update` / `+record-get` / `+record-list`，且参数是 `--base-token` + `--json`（而非 `--app-token` + `--fields`）。
- **卡片命令不存在**：`im +send-card` / `im +update-card` 不存在。发卡改用 `im +messages-send --msg-type interactive --content <卡片JSON>`，收件人 flag 为 `--user-id`（ou_）或 `--chat-id`（oc_），非 `--receive-id`；更新卡片无快捷命令，需 `lark-cli api PATCH /open-apis/im/v1/messages/{message_id}`。
- **任务命令部分错误**：`task +get` 不存在；`task +update` 无 `--status`，改状态须走 `task +complete` / `task +reopen`。
- **妙记参数与取值方式错误**：`minutes +search` 是 `--start` / `--end`（非 `--start-time` / `--end-time`）；`minutes +detail` 是 `--minute-tokens`（复数），且 `--transcript` 将逐字稿**写入文件**（`--output-dir`，默认 `./minutes/{minute_token}/`）而非 stdout，现有 `json.loads(result.stdout)` 取不到逐字稿。

## What Changes

- 四个适配器的 `_real_*` 方法全部对齐 v1.0.86 的真实命令、参数与身份传递方式。
- 妙记详情读取改为「调用 → 定位输出目录 → 读取落盘的逐字稿 → 解析」。
- 卡片发送改用 `im +messages-send --msg-type interactive`；卡片更新改走 `lark-cli api`。
- 任务状态更新按目标状态分派到 `+complete` / `+reopen`。
- 规格补充：新增「lark-cli 调用契约」与「妙记逐字稿落盘读取」需求；修改「运行模式隔离」，把凭据来源从 `.env` token 更正为 lark-cli 钥匙串。
- 清理 `config/env.example` 与 `config/.env` 中失效的两个 token 字段。

## Non-goals

- 不改 Mock 模式行为，不改状态机、幂等、重试、集成日志。
- 不改平台侧接口契约（`contracts/`）。
- 不实现卡片按钮回调的 CLI 侧接收（回调仍由本项目 webhook 处理）。
- 不追求「无凭据也能验证真实调用」：`--dry-run` 已可验证请求体，但真实发送仍依赖使用者完成 `lark-cli auth login`。

## Impact

- 受影响代码：`adapters/minutes_adapter.py`、`adapters/task_adapter.py`、`adapters/im_card_adapter.py`、`adapters/base_adapter.py`、`adapters/docs_adapter.py`、`config/env.example`。
- 受影响规格：`meeting-ingest`、`feishu-actions`、`orchestration-reliability`。
- 验证边界：所有改动后的命令用 `--dry-run` 逐条核对请求体；Mock 模式全量测试与 demo 回归。**真实端到端（尤其读私有妙记）需要 `lark-cli auth login` 完成 user 身份授权后由使用者验证**，本 change 不声称已完成真实链路验证。
