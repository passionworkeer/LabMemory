# decision-compiler 规格增量

## ADDED Requirements

### Requirement: Aily 技能编译
系统 SHALL 调用 Aily 技能（`POST {AILY_API_BASE}/v1/skills/{AILY_SKILL_ID}/run`）把 `MeetingPackage` 编译为 `CandidatePackage`，编译输出 MUST 符合 `contracts/candidate-package.schema.json` 且携带 `aily_skill_version` 与 `source_package_id` 以保证可追溯。

#### Scenario: 正常编译
- GIVEN 一份含逐字稿的 `MeetingPackage`
- WHEN 系统调用 Aily 技能编译
- THEN 系统 SHALL 产出 `CandidatePackage`，其中每个候选包含 `candidate_id`、`type`、`title`、`confidence`、`evidence`、`status`

#### Scenario: 编译前置状态
- GIVEN 编排进入编译阶段
- WHEN 系统开始调用 Aily
- THEN 编排状态 SHALL 迁移为 `compiling`，编译成功后 SHALL 迁移为 `submitted`

### Requirement: Aily 只能产出候选
Aily 编译结果 MUST 全部以「候选」状态提交，MUST NOT 直接产出当前有效参数、正式主张或正式任务（与 trust-rules 主张状态机一致）。

#### Scenario: 模型给出高置信结论
- GIVEN Aily 对某参数给出 `confidence` 为 0.95 的结论
- WHEN 候选提交平台
- THEN 该候选状态 SHALL 仍为候选并进入决策收件箱，MUST NOT 跳过人工复核直接生效

### Requirement: 证据锚点必填
每个候选 MUST 携带指向妙记的证据锚点（发言人与时间偏移）；无法定位证据的候选 MUST 显式标记证据缺失，MUST NOT 编造时间戳或发言人。

#### Scenario: 无法定位原文
- GIVEN 某候选来自模型归纳、无法对应到具体逐字稿片段
- WHEN 系统组装 `CandidatePackage`
- THEN 该候选的 `evidence` SHALL 标记为证据缺失，并由平台侧证据门限制其不得成为当前有效

### Requirement: 编译失败处理
Aily 调用失败或返回结构不符合契约时，系统 MUST NOT 提交平台；SHALL 将编排状态置为 `failed`、记录失败集成日志，并保留 `MeetingPackage` 以便重放。

#### Scenario: Aily 返回非法结构
- GIVEN Aily 返回缺少 `candidates` 字段的响应
- WHEN 系统校验编译结果
- THEN 系统 SHALL 判定编译失败、不调用平台提交接口，并支持按 `source_id` 重放

### Requirement: 编译降级入口
系统 SHALL 提供纯文本输入的编译入口，用于妙记不可用时的降级演示；该入口产出的 `MeetingPackage` MUST 标记来源为手工输入，不得冒充真实妙记。

#### Scenario: 手工文本触发编译
- GIVEN 妙记接口不可用，改为粘贴会议文本
- WHEN 系统以文本入口触发编译
- THEN `MeetingPackage.source` SHALL 标记为手工输入来源，后续链路行为与妙记入口一致
