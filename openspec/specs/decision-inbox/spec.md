# Decision Inbox Specification

## Purpose
承接 Aily 编译产生的候选对象（参数、主张、争议、风险、任务），完成三值复核、证据确认与受控发布，是会议判断进入可信知识前的统一收件箱。

## Requirements

### Requirement: 三值对比
系统 SHALL 在决策收件箱中并列展示「原始会议表达 / AI 候选值 / 人工确认值」三值；任何人工修改 MUST 填写或选择修改原因。

#### Scenario: 修正 AI 误识别
- GIVEN Aily 将「下一轮可以降到 0.8 eq」识别为最终参数
- WHEN 负责人在收件箱修正为「待验证建议」并填写原因
- THEN 系统 SHALL 保留 AI 原值与人工修正值，并创建复验任务草稿而不发布为当前有效参数

### Requirement: 语义分类
系统 SHALL 将候选区分为事实、建议、计划、假设、风险、任务、争议；「可以试试 / 建议 / 可能 / 暂定」等表达 MUST NOT 成为当前有效参数。

#### Scenario: 条件性建议不得成为最终参数
- GIVEN 原文为条件性建议且尚无实验结果
- WHEN 候选进入发布闸门
- THEN 系统 SHALL 将其状态限制为「待验证」，默认不允许成为高可信问答依据

### Requirement: 证据定位
正式主张 MUST 绑定有效证据（妙记时间戳、发言人、实验结果文件或受控文档）；证据失效时 MUST NOT 发布为当前有效。

#### Scenario: 证据失效降级
- GIVEN 某主张关联的证据链接失效
- WHEN 系统检测到证据状态为失效
- THEN 系统 SHALL 降低该主张可信状态并停止主动推荐，通知责任人修复

### Requirement: 发布闸门
系统 MUST 在发布正式对象前运行六道质量闸门（见 trust-rules 规格）；参数变更与高风险候选 MUST NOT 进入批量发布。

#### Scenario: 高风险候选单独处理
- GIVEN 候选为参数变更或高风险项
- WHEN 用户尝试批量确认
- THEN 系统 SHALL 拒绝批量发布，要求逐条进入决策收件箱处理
