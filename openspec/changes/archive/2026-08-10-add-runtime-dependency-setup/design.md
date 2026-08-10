## Context

`core/config.py` 需要 `python-dotenv` 读取 `.env`，但依赖文件与部署指引没有随代码提交。Windows 控制台默认编码也可能无法输出中文日志。

## Goals / Non-Goals

**Goals:**

- 让干净 Python 环境可通过一个依赖文件安装编排器所需的第三方库。
- 确保可重配置的标准输出使用 UTF-8。

**Non-Goals:**

- 不改变 `.env` 的位置、加载优先级或飞书业务逻辑。
- 不增加新的日志框架或运行时配置机制。

## Decisions

- 使用 `requirements.txt` 声明 `python-dotenv>=1.0.0`，因为项目已经以 pip 虚拟环境作为部署路径；不引入新的打包工具。
- 在 `config.py` 启动阶段调用 `sys.stdout` 与 `sys.stderr` 的 `reconfigure`（若支持）。不支持时保持原状，以兼容重定向流和非 Windows 环境。

## Risks / Trade-offs

- [部分输出流不支持 `reconfigure`] → 仅在属性存在时调用并安全降级。
- [依赖版本未来出现不兼容] → 保留最低兼容版本约束并由部署测试验证安装。
