## ADDED Requirements

### Requirement: 编排器运行时依赖可安装
飞书编排器 MUST 提供可由 pip 使用的依赖清单，其中 SHALL 包含用于加载 `.env` 文件的 `python-dotenv` 依赖；部署文档 MUST 指引使用该清单安装依赖。

#### Scenario: 在干净虚拟环境中安装依赖
- **WHEN** 部署人员在已激活的 Python 虚拟环境中执行 `pip install -r requirements.txt`
- **THEN** 安装结果 SHALL 包含可供 `core.config` 导入的 `dotenv` 模块

### Requirement: 中文日志输出兼容
编排器在标准输出流支持重新配置时 MUST 将标准输出和标准错误输出配置为 UTF-8，以避免中文日志引发编码异常。

#### Scenario: Windows 控制台输出中文日志
- **WHEN** 编排器在可重新配置输出流的 Windows 控制台中输出中文日志
- **THEN** 日志写入 SHALL 不因控制台默认编码而抛出 `UnicodeEncodeError`
