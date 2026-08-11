# feishu-actions Specification Delta

## ADDED Requirements

### Requirement: 卡片回调分流不静默成功
系统 SHALL 对平台返回的卡片回调结果显式分流：`status=approved AND action_audit=pass` → 创建飞书任务；`status=rejected` → 驳回处理；`status=blocked` → 发阻断卡；其余（`needs_confirmation`/`revise`/未知）→ 记 needs_confirmation/blocked 状态。MUST NOT 对未过审计的回调静默记录 `status=success`。流水线 SHALL 返回 `status="submitted"`（非 `success`+`completed_at`），如实反映「已提交待复核」而非「已完成」。

#### Scenario: needs_confirmation 不记 success
- GIVEN 平台回调返回 `status=blocked, action_audit=needs_confirmation`
- WHEN 编排器处理
- THEN 系统 SHALL 记 needs_confirmation/blocked 状态，MUST NOT 记 success 或 completed_at

### Requirement: Aily 候选边界强制
系统 SHALL 无条件强制每个 Aily 候选的 `status="candidate"` 与 `needs_review=True`，MUST NOT 仅在字段缺失时补默认（防止 Aily 返回 `approved`/`needs_review:false` 越过候选边界直接生效）。

#### Scenario: Aily 返回 approved 被强制降级
- GIVEN Aily 编译返回某候选 `status="approved"`
- WHEN 编排器组装 CandidatePackage
- THEN 该候选 SHALL 被强制为 `status="candidate", needs_review=True`

### Requirement: 卡片动作类型统一为 approve
系统 SHALL 统一卡片按钮 `action_type` 取值为 `approve`/`revise`/`reject`（对齐平台 `Literal`），MUST NOT 接受 `approved`/`rejected` 等过去式别名（否则真实平台 422）。Mock 与夹具 SHALL 与真实平台同款取值。

#### Scenario: approved 别名不被接受
- GIVEN 编排器 mock 客户端收到 `action_type="approved"`
- WHEN 转发真实平台
- THEN 系统 MUST NOT 兼容该别名；夹具与测试 SHALL 统一用 `approve`
