# decision-inbox Specification Delta

## ADDED Requirements

### Requirement: 三值留痕与修改原因
系统 SHALL 保留三值：原始会议表达（`Meeting.raw_payload`+transcript）、AI 候选（`Candidate.candidates`）、人工确认值（`MeetingReview.modifications`）。任何人工修改 MUST 记录修改人（`MeetingReview.reviewer_id`）与原因（`ReviewConfirmIn.reason`/`notes`，写入 AuditEvent）。

#### Scenario: 人工修改记录原因
- GIVEN 复核人确认候选并把浓度从 0.20 改为 0.25
- WHEN 提交复核（modifications + reason「浓度由实验结果校正」）
- THEN 系统 SHALL 在 MeetingReview.modifications 记录新值，并在 AuditEvent 记录修改人 + reason
