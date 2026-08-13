## Context

所有 adapter 当前在命令数组首位硬编码 `lark-cli`。Windows npm 全局安装通常提供 `lark-cli.cmd`，Python subprocess 的路径解析与 PowerShell 不同，导致同一环境出现“shell 可执行、服务不可执行”。

## Decisions

1. 在 `Config` 提供 `LARK_CLI_COMMAND`：优先使用环境变量；未配置时 Windows 选择 `lark-cli.cmd`，其他系统选择 `lark-cli`。
2. adapter 命令统一通过一个本地 helper 生成首个命令元素，不改动其余参数。
3. 启动/health check 可报告最终解析的命令；若命令仍不可执行，错误信息同时包含命令名和安装/PATH 建议。
4. 测试通过 patch 平台系统与环境变量验证选择逻辑，并用现有 subprocess mock 验证 adapter 使用解析结果。

## Non-Goals

- 不使用 `shell=True`，避免引入命令注入风险。
- 不自动安装 npm 包。
- 不修改 lark-cli credentials/keychain 行为。
