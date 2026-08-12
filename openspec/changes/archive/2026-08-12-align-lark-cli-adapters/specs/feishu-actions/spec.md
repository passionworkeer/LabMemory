# feishu-actions 规格增量

## ADDED Requirements

### Requirement: lark-cli 调用契约
系统 SHALL 通过飞书官方 CLI（`lark-cli`，npm 包 `@larksuite/cli`）执行所有飞书出向动作。调用身份 MUST 通过 `--as user|bot` 指定，MUST NOT 通过命令行参数传递 access token（真实 CLI 无此参数，凭据由 CLI 自身的系统钥匙串管理）。适配层使用的命令名与参数名 MUST 与已安装 CLI 版本的 `--help` 签名一致；CLI 不存在的能力 MUST 降级到 `lark-cli api` 原始调用，MUST NOT 保留不存在的子命令。

#### Scenario: 发送交互卡片
- GIVEN 需要向复核人下发交互卡片
- WHEN 系统调用 CLI
- THEN 系统 SHALL 使用 `im +messages-send --msg-type interactive --content <卡片JSON>`，收件人 SHALL 通过 `--user-id`（ou_ 开头）或 `--chat-id`（oc_ 开头）指定

#### Scenario: 更新卡片无快捷命令
- GIVEN 需要更新已发送的卡片
- WHEN 系统发现 CLI 无对应快捷命令
- THEN 系统 SHALL 通过 `lark-cli api PATCH /open-apis/im/v1/messages/{message_id}` 完成，MUST NOT 调用不存在的 `im +update-card`

#### Scenario: 任务状态更新
- GIVEN 需要把任务标记为完成或重新打开
- WHEN 系统更新任务状态
- THEN 系统 SHALL 按目标状态分派到 `task +complete` 或 `task +reopen`，MUST NOT 依赖 `task +update --status`（该参数不存在）

#### Scenario: 多维表格写入
- GIVEN 需要写入或更新协同看板记录
- WHEN 系统调用 CLI
- THEN 系统 SHALL 使用 `base +record-batch-create` / `base +record-batch-update`，参数为 `--base-token`、`--table-id` 与 `--json`

#### Scenario: 知识文档发布
- GIVEN 需要发布知识文档
- WHEN 系统调用 CLI
- THEN 系统 SHALL 使用 `docs +create --title --content --doc-format markdown`，读取使用 `docs +fetch --doc`，MUST NOT 使用不存在的 `docx` 域

### Requirement: CLI 缺失与授权缺失的可诊断失败
当 `lark-cli` 未安装、未绑定配置或未完成身份授权时，系统 MUST 以明确原因失败并记录失败集成日志，MUST NOT 静默退回 Mock 数据。

#### Scenario: 未完成 user 授权
- GIVEN Real 模式下需要以 user 身份读取资源但未执行 `lark-cli auth login`
- WHEN 系统发起调用
- THEN 系统 SHALL 判定失败并在错误信息中指出需要完成 CLI 授权，MUST NOT 返回模拟数据冒充真实结果
