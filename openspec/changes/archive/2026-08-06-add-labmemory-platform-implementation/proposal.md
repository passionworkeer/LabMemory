# Proposal: Add LabMemory Platform Implementation

## Why

LabMemory 仓库已有 `feishu-orchestrator/` 子模块（飞书侧妙记接入、Aily 编译、卡片下发），但缺少**自研平台内核**：接收候选包后的人工复核、参数版本管理、行动前审计、结果回流与知识卡生成。`labmemory-platform/` 目录当前只有一个断裂的脚手架（每模型独立 Base、import 路径不一致、schema 与契约不符），无法运行。

本 change 实现 docx《LabMemory 自研平台与可信决策系统负责人工作说明》定义的 M1-M5 全部里程碑，使平台可作为独立可运行系统承载复赛 Demo 的三条主线：决策收件箱（0.8eq->待验证）、行动前审计（80℃->70℃ 阻断+一键修正）、结果回流（65℃->部分支持+失败卡）。

## What Changes

- **新增** `labmemory-platform/` 完整实现：FastAPI + PostgreSQL + Alembic + Pydantic v2，22 张领域表，4 个契约端点（`/v1/candidates`、`/v1/card/callback`、`/v1/task/status`、`GET /v1/candidates/{id}`），17 个前端端点，6 道质量闸门，5 类行动审计检查，3 态审计结论，状态机（候选/主张/参数版本/任务/结果/集成动作），Mock 飞书适配器，种子数据（Story A 80℃->70℃ + Story B 65℃ 部分支持），前端接线（复用 `附件/index.html` 视觉结构），Docker Compose 一键启动，全套测试。
- **新增** OpenSpec 规格（仅 ADDED，不改已有 specs）：
  - `control-tower`：研发控制塔看板与异常队列
  - `experiment-passport`：实验护照跨对象时间线与双向证据
  - `platform-permissions`：5 角色与项目成员权限
  - `platform-audit-trail`：AuditEvent 覆盖所有正式状态变更
- **不修改** `feishu-orchestrator/`、`openspec/specs/` 已归档源真相、`附件/`。

## Boundary with feishu-orchestrator

平台只依赖 `openspec/specs/contracts/` 定义的 4 个契约对象（`MeetingPackage`、`CandidatePackage`、`FeishuActionRequest`、`CardCallback`），不直接调用 lark-cli、Aily Skill 或飞书任务接口。所有外部动作写入 `IntegrationAction` 表，由飞书编排服务异步执行（Mock 模式下由进程内 `MockFeishuClient` 模拟）。

## Impact

- 新增 ~120 个源文件（Python 后端 + HTML/JS 前端 + 测试 + Docker + 种子）
- 平台可独立运行（`docker compose up`），也可与 feishu-orchestrator 联调（`FEISHU_ORCHESTRATOR_MODE=real`）
- 现有 `openspec/specs/` 不变；本 change 归档时 4 个新 spec 域合入源真相
