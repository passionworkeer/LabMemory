## Why

飞书编排器已通过 `dotenv` 加载本地配置，但仓库未声明该运行时依赖，部署说明也仍将其描述为仅使用标准库。这会使干净环境无法可靠启动服务。

## What Changes

- 声明飞书编排器的 `python-dotenv` 运行时依赖，并更新部署安装步骤。
- 在 Windows 本地与演示控制台中将标准输出和错误输出配置为 UTF-8，避免中文日志导致编码异常。

## Capabilities

### New Capabilities

- `runtime-configuration`: 定义飞书编排器在干净环境中的依赖安装与中文日志输出要求。

### Modified Capabilities

- 无。

## Impact

- `feishu-orchestrator/feishu-orchestrator/core/config.py`
- `feishu-orchestrator/feishu-orchestrator/requirements.txt`
- `feishu-orchestrator/feishu-orchestrator/DEPLOYMENT.md`
