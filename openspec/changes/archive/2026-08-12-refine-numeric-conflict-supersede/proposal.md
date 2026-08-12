# Proposal: 明确数值冲突与复核确认 supersede 的边界（§10.5 ↔ §10.3 reconciliation）

## Why

`openspec/specs/trust-rules/spec.md` 现有两条 Requirement 存在内部张力：

- 「冲突检测」「发布前冲突检测」把「同 scope 同参数名不同值」一律判数值冲突、MUST 冻结；
- 「参数版本按参数维度跟踪」要求新主张 supersede 旧 current 时按参数维度升版（值变化→升版），隐含「经复核确认替换单条 current」是受支持的版本更新路径。

实现侧 `app/services/trust_rules.py` 的 `detect_conflicts` 在 `_build_claim` supersede **之前**执行，且不排除将被替换的当前 current，导致**任何同 scope 值变更都会自冲突冻结**——正常的人工复核更新参数流程不可用。e2e 测试 `scripts/e2e_test.py:303` 不得不用「与当前主张完全相同的值」来回避数值冲突，才能验证 supersede（注释明写「避免数值冲突」）。这与 §10.3 版本演进模型直接矛盾，使「版本不覆盖、可更新」的核心卖点落空。

## What Changes

- MODIFIED `specs/trust-rules/spec.md`「冲突检测」「发布前冲突检测」：把数值冲突界定为「发布后将出现**未被本次 supersede 替换的**多个 current、同 scope 同参数不同值」的并存歧义；经复核确认按 §10.3 替换唯一 current 的版本更新不构成数值冲突、不冻结。各补一个 Scenario 说明边界。

## Non-goals

- 不改动版本冲突、范围冲突、语义冲突、证据冲突、责任冲突的判定规则。
- 不改动「参数版本按参数维度跟踪」（§10.3）的文本——本次只解 §10.5 侧的过冻结。
- 不触碰 trust-rules 以外领域规格。

## Impact

- 受影响规格：`specs/trust-rules/spec.md`
- 受影响实现：`app/services/trust_rules.py` `detect_conflicts`（排除将被 supersede 的最新 current）；`scripts/e2e_test.py` 第二次会议改为「值变更」验证 supersede + 升版。
- 归档后 `openspec validate` 通过。
