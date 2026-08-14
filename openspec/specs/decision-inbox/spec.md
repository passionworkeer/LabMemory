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

### Requirement: 三值留痕与修改原因
系统 SHALL 保留三值：原始会议表达（`Meeting.raw_payload`+transcript）、AI 候选（`Candidate.candidates`）、人工确认值（`MeetingReview.modifications`）。任何人工修改 MUST 记录修改人（`MeetingReview.reviewer_id`）与原因（`ReviewConfirmIn.reason`/`notes`，写入 AuditEvent）。

#### Scenario: 人工修改记录原因
- GIVEN 复核人确认候选并把浓度从 0.20 改为 0.25
- WHEN 提交复核（modifications + reason「浓度由实验结果校正」）
- THEN 系统 SHALL 在 MeetingReview.modifications 记录新值，并在 AuditEvent 记录修改人 + reason

### Requirement: 复核确认的并发串行化

复核状态检查与状态变更 MUST 完整位于按实验的写锁临界区内：进入临界区后复查 `review.status == "pending"`，非 pending SHALL 抛出状态转移错误。Web 复核路径与卡片回调 approve 路径 MUST 遵循同一串行化纪律。

#### Scenario: 并发确认同一会议

- GIVEN 会议 M 复核记录状态为 pending
- WHEN 两个确认请求并发到达
- THEN 仅第一个 SHALL 成功；第二个 SHALL 在锁内复查发现非 pending 并返回状态转移错误，不产生重复 Claim/Task

### Requirement: 卡片回调发布的主张进入检索索引

卡片回调 approve 路径生成 current 主张后，系统 SHALL 与 Web 复核路径一致地触发主张索引与会议证据索引；supersede 旧主张时 SHALL 同步把旧主张检索切片标记为 superseded。

#### Scenario: 卡片审批后的问答可见性

- GIVEN 候选经飞书卡片 approve 发布为 current 主张 C2，同实验旧主张 C1 被替代
- WHEN 用户向可信问答提问相关参数
- THEN 检索候选集 SHALL 含 C2 且不含 C1（C1 切片状态为 superseded）

### Requirement: 索引失败的可见性

主张/结果/证据索引更新失败时，系统 SHALL 记录告警日志（含失败对象与异常摘要），不得静默吞异常；失败不得阻断业务主流程。

#### Scenario: 索引异常留痕

- GIVEN 索引更新抛出异常
- WHEN 复核确认流程执行
- THEN 业务提交 SHALL 正常完成，且日志 SHALL 包含索引失败告警

