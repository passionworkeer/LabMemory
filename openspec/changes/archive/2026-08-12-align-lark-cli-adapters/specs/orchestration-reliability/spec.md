# orchestration-reliability 规格增量

## MODIFIED Requirements

### Requirement: 运行模式隔离
系统 SHALL 通过 `RUN_MODE` 区分运行模式，默认为 `mock`。`mock` 模式下 MUST NOT 发起任何真实飞书 / Aily / 平台调用。切换为真实模式 MUST 依赖显式配置的凭据，缺失凭据时 SHALL 明确报错，MUST NOT 静默退回 mock。

凭据来源按调用目标区分，MUST NOT 混用：

- **飞书调用**：凭据由 `lark-cli` 自身管理（`lark-cli config bind` / `config init` + `auth login`，存于操作系统钥匙串）。系统 MUST NOT 从 `.env` 读取或向 CLI 传递飞书 access token。
- **Aily 与平台调用**：走 HTTP，凭据 MUST 来自 `config/.env`（`AILY_API_KEY`、`PLATFORM_API_KEY`）。

#### Scenario: 默认零凭据可运行
- GIVEN 未配置任何飞书或 Aily 凭据
- WHEN 系统启动并执行完整主链路演示
- THEN 系统 SHALL 以 mock 模式跑通全链路，所有外部调用 SHALL 由本地模拟返回

#### Scenario: 真实模式缺失凭据
- GIVEN `RUN_MODE=real` 但 Aily 或平台的 API Key 未配置
- WHEN 系统发起对应调用
- THEN 系统 SHALL 失败并提示缺失的配置项名称，MUST NOT 以 mock 行为伪装成真实运行

#### Scenario: 飞书凭据不在 .env 中
- GIVEN `RUN_MODE=real` 且 `lark-cli` 已完成绑定与授权
- WHEN 系统发起飞书调用
- THEN 系统 SHALL 仅通过 `--as user|bot` 声明身份并由 CLI 解析凭据，`.env` 中的飞书 token 字段 SHALL 不参与调用
