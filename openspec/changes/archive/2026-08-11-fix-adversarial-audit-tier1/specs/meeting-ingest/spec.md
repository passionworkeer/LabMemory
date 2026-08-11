# meeting-ingest Specification Delta

## ADDED Requirements

### Requirement: 编排器提交候选前注册会议
飞书编排器 SHALL 在向平台 `POST /api/v1/candidates` 之前，先 `POST /api/v1/meetings` 注册 `MeetingPackage`，使平台能按 `source_package_id` 回溯到会议。`MeetingPackage.metadata` MUST 携带 `experiment_id`（从 CLI 参数 / 会议映射表 / 日历获取），MUST NOT 为空对象。CandidatePackage 的 `source_package_id` MUST 等于已注册会议的 `meeting_id`。

#### Scenario: 候选提交前注册会议
- GIVEN 编排器从妙记编译出 CandidatePackage
- WHEN pipeline 执行
- THEN 系统 SHALL 先 POST /api/v1/meetings（含 experiment_id），再 POST /api/v1/candidates，且 candidate 的 source_package_id == 会议 meeting_id

#### Scenario: metadata 缺 experiment_id 不提交
- GIVEN 编排器组装的 MeetingPackage.metadata 不含 experiment_id
- WHEN pipeline 执行
- THEN 系统 MUST NOT 提交， SHALL 报错提示 experiment_id 缺失
