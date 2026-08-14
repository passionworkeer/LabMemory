# Proposal: fix-trust-core-round3（对抗审查第三轮·可信内核 P0）

## Why

第三轮对抗审查发现可信内核存在系统性击穿：六道闸门的范围门结论与落库结果脱节（候选 scope 不落库 → 冲突检测不可达）、语义栅栏可经复核修改绕过、并发确认重复建 Claim/Task、行动前审计通过后版本变更不复查、supersede 后旧主张检索切片不降级、卡片回调路径完全不进 RAG 索引。这些直接击穿「冲突检测」「语义栅栏」「问答排除失效主张」「行动前审计拦截旧版本」四个已宣称 ✅ 的卖点。

## What Changes

1. **scope 贯通**：`_build_claim` 的 `parameter_version.scope` 改用 `trust_rules._scope`（候选自带 scope 作为回退），卡片回调路径同样受益；`confirm_review` 计算 `new_scope` 同步修正。
2. **语义栅栏扫描修改值**：`run_six_gates` 状态门的扫描文本加入 `modifications.title` 与修改/候选参数值文本。
3. **锁内复查复核状态**：`confirm_review` 把 `r.status != "pending"` 检查移入 `lock_experiment_for_write` 临界区（与 card_callback 对齐）。
4. **启动任务复查版本**：`start_task` 校验任务绑定 claim 仍为该实验 current 且 knowledge_status 不属于 refuted/replaced/insufficient_evidence；不满足则置 needs_confirmation 并提示一键修正。
5. **索引同步**：`confirm_review` supersede 旧主张后调用 `mark_claim_superseded`；`card_callback` approve 路径补 `index_claim`/`index_meeting`；索引异常记录告警日志不再静默 `pass`。
6. **supersede 按 scope 匹配**：发布 current 时仅 supersede 与新主张 scope 等价的旧 current（`_scope_eq`），不同 scope 的 current 并存——与冲突检测「多 current 并存但 scope 区分」的模型对齐。
7. **数值口径统一**：参数继承判定改用 `_value_key` 归一化（70 == 70.0 == "70"），与冲突检测一致。
8. **审计写路径加锁**：`audit_fix`、`run_audit` 纳入 `lock_experiment_for_write`，防并发双写。
9. **refuted 主张拦截**：`_run_checks` 版本门在 claim.knowledge_status ∈ {refuted, replaced, insufficient_evidence} 时判 needs_confirmation（不阻断但显式提示），防执行已被推翻参数。

## Impact

- 代码：`app/api/meetings.py`、`app/api/integration.py`、`app/api/tasks.py`、`app/services/trust_rules.py`、`app/services/indexer.py`
- 规格：trust-rules、decision-inbox、action-audit、decision-qa
- 风险：中——supersede 语义从「全局唯一 current」改为「per-scope current」，与 detect_conflicts 现行设计一致；种子数据单 scope 场景行为不变。
