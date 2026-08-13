## 1. CLI 命令解析

- [x] 1.1 在 `core/config.py` 增加跨平台 `LARK_CLI_COMMAND` 解析和环境变量覆盖
- [x] 1.2 将五个 adapter 的硬编码 `lark-cli` 替换为统一命令配置
- [x] 1.3 CLI 不存在时输出包含安装和 PATH 建议的错误

## 2. 测试与文档

- [x] 2.1 增加 Windows `.cmd`、Unix 命令和显式配置覆盖测试
- [x] 2.2 验证 Base、Docs、Task 真实调用使用解析后的命令
  - 已实际到达飞书 API；Base 写入因缺少 `base:record:create` scope 被拒绝
- [x] 2.3 更新 `DEPLOYMENT.md` 的 Windows PATH/`.cmd` 说明
- [x] 2.4 运行完整测试、health check、dry-run 和 OpenSpec 严格校验
- [~] 2.5 完成真实 Base 写入/回读验收，并继续执行已提供的 Docs/Task 验收
  - Python 已正确解析并执行 `lark-cli.cmd`，Base API 已实际到达；写入阻塞于 `base:record:create`；Docs 读取成功；Task 读写阻塞于 `task:task:read` / `task:task:write`

## 3. 归档

- [ ] 3.1 归档 `cross-platform-lark-cli` 并同步主规格
