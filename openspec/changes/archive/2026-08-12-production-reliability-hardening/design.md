## Context

当前真实模式的外部调用分散在多个 adapter 中，部分入口已有 `with_retry` 和 `integration_log`，部分入口直接调用 subprocess 并吞掉异常。妙记详情依赖 CLI 返回路径，Aily 输出解析也存在“失败转空结构”的降级。实现必须保持 Mock 流程兼容，并沿用现有重试引擎、集成日志和持久化幂等设施。

## Goals / Non-Goals

**Goals:**

- 建立统一的真实外部调用失败边界：异常类型、失败日志和重试判定一致。
- 让成功结果具备可验证的资源 ID，避免假成功进入后续状态机。
- 固定妙记逐字稿输出目录并限制读取范围。
- 为关键出向动作补齐重试、日志和可恢复的幂等信息。
- 用 subprocess mock 测试验证命令、响应解析和失败路径。

**Non-Goals:**

- 不更换 lark-cli、Aily 或平台 API。
- 不改变既有 Mock 数据和业务状态机语义。
- 不重构全部 adapter 目录，只抽取确实复用的错误/调用辅助逻辑。
- 不声称完成真实飞书端到端验收；真实验收仍需用户环境和权限。

## Decisions

1. **统一外部异常分类**：在重试引擎中支持标准 `TimeoutError`、`ConnectionError` 及显式 `RetryableError`，各 adapter 保留原始异常链并使用明确的 `NonRetryableError` 表示授权、参数和响应契约错误。中文用户提示通过异常消息表达，但不作为唯一重试判据。
2. **固定逐字稿目录**：使用 `Config.DATA_DIR / "minutes" / minute_token` 作为每次详情调用的输出目录，调用时显式传 `--output-dir`；CLI 返回路径必须解析为该目录下文件，防止工作目录变化和任意路径读取。
3. **结果契约校验**：在 adapter 边界校验 task GUID、record ID、doc token 和 Aily CandidatePackage 必填结构。空查询是合法业务结果，但 subprocess 非零、JSON 非法或结构错误必须抛异常并记录失败。
4. **日志与重试边界**：对每个真实公开入口维持一个重试边界，避免外层批量重试与内层单项重试叠加；调用开始、重试和最终结果使用既有 JSONL 日志。卡片审批后的发送/更新统一复用带日志重试的发送路径。
5. **副作用幂等**：任务创建优先使用 candidate_id 作为稳定业务键进行本地/平台侧查重；批量台账写入逐项记录已成功的 record_id，并在重试或恢复时跳过已完成项。若 lark-cli 不支持业务键参数，则通过本地持久化恢复记录和创建前查询实现。
6. **Aily 解析失败不降级**：仅对满足 CandidatePackage 结构的响应返回成功；无法提取合法 JSON 或候选数组类型错误时抛出契约错误，保留原始输出的脱敏摘要用于诊断，不提交平台。

## Risks / Trade-offs

- [CLI 输出格式差异] → 使用返回路径与结构化 JSON 的兼容读取，并在测试中覆盖多种响应包装；真实环境首次调用仍需人工验收。
- [重试导致重复副作用] → 只在可重试异常上重试，并为任务/台账操作保存稳定业务键和已成功资源 ID。
- [严格路径限制影响旧 CLI] → 允许 CLI 返回预期目录内的绝对路径或相对路径，目录外路径明确失败并记录原因。
- [日志内容扩大] → 继续使用统一脱敏函数，命令参数和响应摘要不得写入明文 access token、secret 或 app token。

## Migration Plan

1. 在 Mock 模式运行现有集成、Phase 3、health check 和 demo。
2. 在绑定 Hermes 应用、完成 user/bot 授权后，使用 `--dry-run` 与最小真实资源逐项验收妙记、卡片、任务、Base 和 Docs。
3. 设置 `RUN_MODE=real`，先以单实例运行并观察 `data/integration_logs/` 中的失败和重试记录。
4. 如真实验收失败，回退 `RUN_MODE=mock`；代码回滚使用本 change 的归档前版本，不删除已产生的飞书资源，按日志中的资源 ID 做人工核对。
