## Why

在 Windows 的 Python `subprocess.run(shell=False)` 中，npm 安装生成的 `lark-cli.cmd` 不能可靠地以裸命令名 `lark-cli` 解析；交互式 PowerShell 可以运行，但项目真实 adapter 会误报“lark-cli 未安装”。这会阻断 Windows 环境下的真实 Base、Docs、Task 和卡片链路。

## What Changes

- 增加跨平台 lark-cli 可执行文件解析：Windows 优先使用 `lark-cli.cmd`，其他系统使用 `lark-cli`。
- 所有 adapter 统一使用解析后的 CLI 命令，保留显式配置覆盖能力。
- 增加 Windows/Unix 命令解析和真实 subprocess 调用测试。
- 更新部署文档，说明 Windows Python 进程的 PATH 与 `.cmd` 解析要求。

## Impact

- 代码：`core/config.py`、五个 Feishu adapter。
- 测试：集成测试增加 CLI 可执行文件解析覆盖。
- 文档：`DEPLOYMENT.md` 增加跨平台 CLI 检查。
- 不改变 lark-cli 参数契约、凭据来源或 Mock 行为。
