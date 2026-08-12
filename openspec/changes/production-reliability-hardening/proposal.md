## Why

Real 模式目前能够构造并执行 lark-cli 命令，但部分外部调用会把 CLI 缺失、授权失败、超时、空响应和网络错误伪装成成功或空结果，逐字稿落盘位置也依赖 CLI 默认工作目录。上线后这些问题会造成任务、台账、文档和卡片状态不一致，且难以从集成日志定位。现在需要在真实链路验收前补齐失败诊断、结果完整性、重试和幂等边界。

## What Changes

- 固定妙记逐字稿的输出目录，读取并校验 CLI 返回的落盘文件。
- 统一真实外部调用的异常传播、失败日志和可重试错误识别。
- 对任务、Base 记录、Docs 文档的成功响应校验必填资源 ID。
- 为查询、任务状态更新、卡片发送与更新等关键真实调用补充可靠性封装。
- 防止 Aily 非法输出被当作空候选包成功处理。
- 为任务创建和批量台账写入增加可恢复的幂等边界，避免超时重试造成重复副作用。
- 增加命令构造、错误诊断、空响应、重试和逐字稿解析测试，并更新上线验收文档。

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `feishu-actions`: 真实外部调用失败必须可诊断，成功响应必须具备必要资源标识，关键出向动作必须遵循可靠性策略。
- `meeting-ingest`: 妙记逐字稿输出目录和读取失败行为必须稳定、可验证。
- `orchestration-reliability`: 外部调用的重试、日志、幂等和失败状态必须一致，不能把失败静默转换成成功。
- `decision-compiler`: Aily 返回不可解析或结构不完整时必须明确失败，不能冒充空结果成功。

## Impact

- 代码：`adapters/minutes_adapter.py`、`adapters/base_adapter.py`、`adapters/task_adapter.py`、`adapters/docs_adapter.py`、`adapters/im_card_adapter.py`、`adapters/aily_adapter.py`、`reliability/retry_engine.py` 及相关调用方。
- 测试：集成测试、Phase 3 测试，以及新增的真实模式 subprocess 模拟测试。
- 文档：`DEPLOYMENT.md` 增加 Real 模式上线前检查、失败日志和真实端到端验收说明。
- 不改变 Mock 模式的业务结果，不改变既有 contracts JSON schema。
