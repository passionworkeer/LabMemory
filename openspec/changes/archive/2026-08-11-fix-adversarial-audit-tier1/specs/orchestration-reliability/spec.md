# orchestration-reliability Specification Delta

## ADDED Requirements

### Requirement: 幂等占位原子化
系统 SHALL 用原子文件创建（`O_CREAT|O_EXCL`）作为幂等占位令牌：业务执行前先尝试创建占位文件，创建成功者获得执行权，失败者视为已处理。MUST NOT 采用「检查→业务→标记」三步非原子序列（存在 TOCTOU 竞态，并发/重试下可重复执行建任务等副作用）。

#### Scenario: 并发同 token 仅执行一次
- GIVEN 两个并发回调携带相同 token
- WHEN 两者同时进入幂等检查
- THEN 系统 SHALL 仅允许其中一个执行业务副作用，另一个直接返回已处理结论

### Requirement: 重试按 HTTP 状态分类
系统 SHALL 按可恢复性分类错误以决定重试：仅 5xx（500/502/503/504）与 429 重试；4xx（除 429）判为不可恢复并立即失败。错误包装 MUST 保留原始 HTTP code，MUST NOT 仅依赖响应体字面字符串（如 "rate limit"）判定。

#### Scenario: 400 不重试
- GIVEN 平台返回 HTTP 400（业务校验错）
- WHEN 编排器重试引擎处理
- THEN 系统 MUST NOT 重试， SHALL 立即抛出不可恢复错误

### Requirement: 卡片回调受理与后续动作分离标记
系统 SHALL 在平台回调转发成功（获得平台响应）后**立即**标记回调「已受理」，与「后续飞书任务创建/卡片发送完成」分离。后续动作失败重试时，平台侧 token 幂等返回首次结论，但编排器 MUST NOT 重复执行建任务等副作用。

#### Scenario: 回调受理后建任务失败不重复
- GIVEN 平台回调返回 approved+pass，编排器标记受理后建飞书任务失败
- WHEN 重试该回调
- THEN 系统 SHALL 跳过 `_handle_approved` 的建任务副作用（已受理），MUST NOT 二次建任务
