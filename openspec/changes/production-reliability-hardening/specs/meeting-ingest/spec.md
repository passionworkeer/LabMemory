## MODIFIED Requirements

### Requirement: 逐字稿落盘读取
`minutes +detail --transcript` MUST 使用按妙记标识隔离的稳定 `--output-dir` 写入逐字稿，而非依赖进程工作目录或标准输出。系统 MUST 在调用后从预期目录读取逐字稿文件，校验文件存在且至少包含一条可解析或原文保留的内容，再组装进 `MeetingPackage`。文件缺失、路径不可读或输出目录不一致时，系统 MUST 记录失败原因并终止编译，MUST NOT 用摘要文本冒充逐字稿。

#### Scenario: 固定目录读取逐字稿
- GIVEN 系统以 `--transcript` 请求指定妙记详情
- WHEN CLI 返回成功且逐字稿写入按妙记隔离的输出目录
- THEN 系统 SHALL 从该目录读取逐字稿并组装进 `MeetingPackage`，且不同妙记的文件 MUST 不互相覆盖

#### Scenario: CLI 返回路径与预期目录不一致
- GIVEN CLI 返回的逐字稿路径不在本次调用的预期输出目录内
- WHEN 系统解析 CLI 结果
- THEN 系统 SHALL 拒绝该路径或明确记录路径不一致失败，MUST NOT 读取任意工作目录文件

#### Scenario: 读取落盘的逐字稿
- GIVEN 系统以 `--transcript` 请求妙记详情
- WHEN CLI 返回成功且逐字稿已写入输出目录
- THEN 系统 SHALL 从输出目录读取逐字稿内容并组装进 `MeetingPackage`

#### Scenario: 逐字稿文件缺失
- GIVEN CLI 调用成功但输出目录中不存在逐字稿文件
- WHEN 系统尝试读取
- THEN 系统 SHALL 判定为逐字稿缺失、记录失败原因并终止编译，MUST NOT 用摘要文本冒充逐字稿

#### Scenario: 逐字稿文件缺失或为空
- GIVEN CLI 调用成功但逐字稿文件不存在、不可读或为空
- WHEN 系统尝试读取
- THEN 系统 SHALL 判定为逐字稿缺失、记录失败原因并终止编译
