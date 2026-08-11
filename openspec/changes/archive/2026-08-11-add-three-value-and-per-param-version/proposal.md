# Proposal: 三值留痕补全 + 参数级版本模型

## Why

AUDIT T2-4/T2-5：
- 三值留痕：原始（Meeting.raw_payload）/AI（Candidate.candidates）已保留，人工值仅 MeetingReview.modifications 自由 dict，缺**修改原因**显式记录（PRD line 297/§0.3「任何人工修改 MUST 记录修改人与原因」）。
- 参数版本：当前以**实验为粒度**整体 supersede 主张、version 实验级 vN+1；改一个催化剂会把未变的温度参数整体升版本、旧温度主张也被 supersede（PRD §10.3 要求「同适用范围同参数仅一个生效版本」）。

## What Changes

- **T2-4**：`ReviewConfirmIn` 增 `reason: str | None` 字段；确认时若有 modifications 但无 reason → warning（仍允许，兼容旧 e2e）。`MeetingReview.notes` 已存原因；AuditEvent 显式记 `reason`。三值位置文档化（raw_payload / candidates / modifications）。
- **T2-5**：`_build_claim` 参数版本改为**按参数跟踪**：supersede 时，新主张每个参数对比旧 current 同名参数——值相同则继承旧版本号（不升版），值变化或新增则升版/置 v1。`parameter_version.parameters[]` 每项携带 `version`；顶层 `version` 取最大值（向后兼容）。未变参数不再被整体升版。

## Impact

- spec：MODIFY `trust-rules`（参数版本按参数维度）、ADDED `decision-inbox`（三值留痕 + 修改原因）。
- 代码：`app/schemas.py`（ReviewConfirmIn.reason）、`app/api/meetings.py:_build_claim`（按参数版本）、`app/api/integration.py`（card_callback 同步）。
- 回归：e2e/pytest/cross_side 全绿（e2e 第二次会议参数与当前一致→继承版本，仍 supersede）。
