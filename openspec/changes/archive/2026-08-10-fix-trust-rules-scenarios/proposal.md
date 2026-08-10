# Proposal: 补齐 trust-rules 缺失的 Scenario 块

## Why

`openspec/specs/trust-rules/spec.md` 的「任务状态机」与「三值留痕」两条 Requirement 缺少 `#### Scenario:` 块，导致 `openspec validate --strict` 对源真相校验不通过，违反 CLAUDE.md 第 0 节红线（源真相必须符合规格格式：每条 Requirement 至少一个 Scenario）。

该问题在 2026-08-05 飞书编排 retro-spec 归档时被标记为遗留项（"属既有源真相缺陷，修复需单独走 change，未在飞书侧提案里夹带平台侧规格变更"），因此单独走本 change 修复，不在飞书侧提案中夹带平台侧规格变更。

## What Changes

- MODIFIED `specs/trust-rules/spec.md`：为「任务状态机」「三值留痕」各补充一个 `#### Scenario:` 块，使其符合 ADDED/MODIFIED 格式要求。两条 Requirement 的语义文本保持不变。

## Non-goals

- 不改动上述两条 Requirement 的语义文本。
- 不触碰其他领域规格（decision-inbox / action-audit / result-backflow / contracts / meeting-ingest / decision-compiler / feishu-actions / orchestration-reliability）。

## Impact

- 受影响规格：`specs/trust-rules/spec.md`
- 归档后 `openspec validate --strict` 对源真相通过。
