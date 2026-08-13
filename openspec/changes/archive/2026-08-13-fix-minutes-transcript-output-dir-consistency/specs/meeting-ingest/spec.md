# meeting-ingest Specification Delta

## MODIFIED Requirements

### Requirement: 逐字稿落盘读取
`minutes +detail --transcript` MUST 使用按妙记标识隔离、且基于 `Config.DATA_DIR` 的稳定 `--output-dir` 写入逐字稿，MUST NOT 使用依赖进程工作目录（cwd）的硬编码相对路径（如 `data/minutes/...`）。落盘目录与传给 lark-cli 的 `--output-dir` MUST 是同一个基于 `Config.DATA_DIR / "minutes" / <minute_token>` 的路径。系统 MUST 在调用后从该目录读取逐字稿文件，校验文件存在且至少包含一条可解析或原文保留的内容，再组装进 `MeetingPackage`。读取 lark-cli 返回的逐字稿路径时，MUST NOT 再次前缀拼接 `Config.DATA_DIR / "minutes"` 造成路径前缀重复。文件缺失、路径不可读或返回路径不在预期输出目录内时，系统 MUST 记录失败原因并终止编译，MUST NOT 用摘要文本冒充逐字稿。

#### Scenario: 基于 DATA_DIR 的稳定输出目录
- GIVEN 系统以 `--transcript` 请求指定妙记详情
- WHEN 系统构造 lark-cli `minutes +detail` 命令
- THEN `--output-dir` SHALL 等于 `Config.DATA_DIR / "minutes" / <minute_token>`，与系统预创建的落盘目录一致，MUST NOT 使用硬编码相对 `data/minutes/...`

#### Scenario: 写入与读取路径一致
- GIVEN lark-cli 在 `--output-dir` 指定目录写入逐字稿，并按该目录返回逐字稿文件路径
- WHEN 系统调用 `_read_transcript_file` 读取逐字稿
- THEN 系统 SHALL 直接使用该路径（当其为基于 `Config.DATA_DIR` 的绝对路径时）读取，MUST NOT 再次前缀拼接 `Config.DATA_DIR / "minutes"` 导致路径重复而找不到文件

#### Scenario: 固定目录读取逐字稿
- GIVEN 系统以 `--transcript` 请求妙记详情
- WHEN CLI 返回成功且逐字稿写入按妙记隔离的输出目录
- THEN 系统 SHALL 从该目录读取逐字稿并组装进 `MeetingPackage`，且不同妙记的文件 MUST 不互相覆盖

#### Scenario: 读取落盘的逐字稿
- GIVEN 系统以 `--transcript` 请求妙记详情
- WHEN CLI 返回成功且逐字稿已写入输出目录
- THEN 系统 SHALL 从输出目录读取逐字稿内容并组装进 `MeetingPackage`

#### Scenario: CLI 返回路径与预期目录不一致
- GIVEN CLI 返回的逐字稿路径不在本次调用的预期输出目录内
- WHEN 系统解析 CLI 结果
- THEN 系统 SHALL 拒绝该路径或明确记录路径不一致失败，MUST NOT 读取任意工作目录文件

#### Scenario: 逐字稿文件缺失
- GIVEN CLI 调用成功但输出目录中不存在逐字稿文件
- WHEN 系统尝试读取
- THEN 系统 SHALL 判定为逐字稿缺失、记录失败原因并终止编译，MUST NOT 用摘要文本冒充逐字稿

#### Scenario: 逐字稿文件缺失或为空
- GIVEN CLI 调用成功但逐字稿文件不存在、不可读或为空
- WHEN 系统尝试读取
- THEN 系统 SHALL 判定为逐字稿缺失、记录失败原因并终止编译，MUST NOT 用摘要文本冒充逐字稿
