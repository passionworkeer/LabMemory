# meeting-ingest 规格增量

## ADDED Requirements

### Requirement: 妙记读取的 CLI 调用契约
Real 模式下系统 SHALL 通过 `minutes +search` 与 `minutes +detail` 读取妙记。时间范围 MUST 使用 `--start` / `--end` 参数；妙记标识 MUST 使用 `--minute-tokens`（支持逗号分隔批量）。

#### Scenario: 按时间范围搜索妙记
- GIVEN 需要按时间范围检索妙记
- WHEN 系统调用 CLI
- THEN 系统 SHALL 传 `--start` / `--end`，MUST NOT 使用不存在的 `--start-time` / `--end-time`

### Requirement: 逐字稿落盘读取
`minutes +detail --transcript` 将逐字稿写入 `--output-dir` 指定目录（默认 `./minutes/{minute_token}/`）而非标准输出。系统 MUST 在调用后从该目录读取逐字稿文件再解析，MUST NOT 假设逐字稿出现在 stdout 的 JSON 中。

#### Scenario: 读取落盘的逐字稿
- GIVEN 系统以 `--transcript` 请求妙记详情
- WHEN CLI 返回成功且逐字稿已写入输出目录
- THEN 系统 SHALL 从输出目录读取逐字稿内容并组装进 `MeetingPackage`

#### Scenario: 逐字稿文件缺失
- GIVEN CLI 调用成功但输出目录中不存在逐字稿文件
- WHEN 系统尝试读取
- THEN 系统 SHALL 判定为逐字稿缺失、记录失败原因并终止编译，MUST NOT 用摘要文本冒充逐字稿

### Requirement: 回调验签的本地 mock 隔离
在 `RUN_MODE=mock` 下，系统仅允许来自本机回环地址的 webhook 请求跳过飞书签名校验。来自非本机地址的请求 MUST 拒绝并返回 HTTP 403；在 `RUN_MODE=real` 下，所有请求仍 MUST 经过时间窗、签名算法和常量时间比较校验。

#### Scenario: 本机 mock 请求跳过验签
- GIVEN `RUN_MODE=mock` 且请求来源为 `127.0.0.1`、`::1` 或 `localhost`
- WHEN webhook handler 校验请求
- THEN 系统 SHALL 接受请求而不要求飞书签名

#### Scenario: 非本机 mock 请求拒绝
- GIVEN `RUN_MODE=mock` 且请求来源不是本机回环地址
- WHEN webhook handler 校验请求
- THEN 系统 SHALL 返回 HTTP 403 并拒绝请求

#### Scenario: real 模式继续验签
- GIVEN `RUN_MODE=real`
- WHEN webhook handler 收到请求
- THEN 系统 SHALL 按飞书签名规则验证请求，过期、篡改或缺失签名的请求 MUST 被拒绝
