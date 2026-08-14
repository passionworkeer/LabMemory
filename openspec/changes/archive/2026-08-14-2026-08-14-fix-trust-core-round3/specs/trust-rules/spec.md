## ADDED Requirements

### Requirement: 候选适用范围贯通落库

系统 SHALL 把候选自带的 `scope`（复核未提供修改时）落入主张 `parameter_version.scope`，与六道闸门范围门的判定输入保持同一来源。卡片回调 approve 路径（无 modifications）MUST 与 Web 复核路径产生等价的 scope 落库结果。

#### Scenario: 候选带 scope 复核不带修改

- GIVEN 会议候选含 `scope={material:"PVA"}`，复核确认未提供 scope 修改
- WHEN 候选通过六道闸门发布为 current
- THEN 主张 `parameter_version.scope` SHALL 等于 `{material:"PVA"}`

#### Scenario: 冲突检测基于已存 scope 生效

- GIVEN 实验 E 已有 current 主张 A（scope={material:"PVA"}，温度 70℃）
- WHEN 新候选 B（scope={material:"PVA"}，温度 80℃）经复核发布
- THEN 数值冲突检测 SHALL 命中同 scope 同参数不同值，发布 SHALL 被冻结为 pending_supplement


### Requirement: 语义栅栏扫描复核修改值

语义栅栏（状态门）MUST 扫描候选原文与复核修改值的合并文本，覆盖 `modifications.title`、`modifications.parameters` 的参数值文本与候选 `title`/`description`。任一命中 hedge 关键词即不得发布为 current。

#### Scenario: 修改标题携带模糊表述

- GIVEN AI 候选 title 为「温度调整为 70℃」（干净）
- WHEN 复核提交 `modifications={"title": "可以试试 70℃"}`
- THEN 状态门 SHALL 命中「可以试试」，发布状态 SHALL 为 pending_validation

### Requirement: 发布 current 时按适用范围替代旧版本

发布新 current 主张时，系统 SHALL 仅 supersede 与新主张 scope 等价（`_scope_eq`）的既有 current 主张；不同 scope 的 current 主张 SHALL 并存。参数继承判定 SHALL 使用与冲突检测一致的数值归一化（`_value_key`：70 == 70.0 == "70"），同值继承不升版。

#### Scenario: 跨范围发布不误杀

- GIVEN 实验 E 有 current 主张 A（scope={material:"PVA"}）
- WHEN 发布新主张 B（scope={material:"PLGA"}）
- THEN A SHALL 保持 current，B SHALL 成为 current 并存

#### Scenario: 同值不同类型不升版

- GIVEN 上一版参数温度值为 70（int）
- WHEN 本次确认提交 70.0
- THEN 该参数 SHALL 继承原版本号，不升版
