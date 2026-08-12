# Design: 数值冲突与复核确认 supersede 的边界

## 决策

数值冲突（§10.5）的本质是防止「同 scope 同参数出现并存且矛盾的多个 current」。而「参数版本按参数维度跟踪」（§10.3）规定：经复核确认的新主张 supersede 旧 current，值变化按参数升版。两者并不矛盾——§10.3 的替换会把旧 current 置 `superseded`，发布后仍只剩一条 current，不产生 §10.5 所防范的并存歧义。

因此判定边界：

- 发布后仍将存在「未被本次 supersede 替换的」多个 current、同 scope 同参数不同值 → 数值冲突，冻结，人工解决。
- 发布会 supersede 唯一/最新 current（其余 current 不受影响）→ 不是冲突，走 §10.3 参数级版本演进。

## 实现要点

`detect_conflicts` 在 `_build_claim`（执行 supersede）**之前**被调用，故它在查询 `status=current` 时仍能看到将被替换的旧 current。需识别「将被替换的最新 current」并排除——选择规则与 `_build_claim` 一致（`status=current` 按 `created_at desc` 取首条）。其余更早的、不会被本次替换的 current 若同 scope 同参数不同值，仍判数值冲突冻结（防御真正的多 current 并存异常）。

## 测试

e2e 第二次会议由「用相同值回避冲突」改为「temperature 70→72 值变更」，验证：新主张 current、旧主张 superseded、温度参数升版（v1→v2），且不再被数值冲突冻结。
