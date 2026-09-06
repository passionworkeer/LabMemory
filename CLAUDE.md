# CLAUDE.md — LabMemory 开发规范

> 本文件是给所有 AI 编程助手（Claude Code / Cursor / CodeBuddy / Codex 等）和团队成员的**强制开发约定**。
> 项目背景、架构、团队分工见 [`README.md`](./README.md)。

---

## 0. 核心红线（必读）

**所有开发必须通过 OpenSpec 规范进行。不允许"先写代码再补文档"，不允许直接改动源真相规格。**

具体强制项：

1. **任何影响系统行为的变更**（新增功能、修改逻辑、新增/修改接口、调整状态机或规则引擎、改动 `contracts/` 接口契约）**必须先创建 OpenSpec change 提案**，并经 `openspec validate` 通过。
2. **不得手动直接编辑 `openspec/specs/` 源真相**。源真相只允许通过 `openspec archive` 把已批准的 change 增量合并进去。
3. **每个 change 必须包含**：`proposal.md`（为什么改、改什么）、`specs/` 增量（ADDED/MODIFIED/REMOVED）、`tasks.md`（实现清单）。复杂变更还应包含 `design.md`（技术决策）。
4. **实现完成后必须 `openspec archive`**，禁止长期挂起未归档的 change；归档即把增量规格合入源真相。
5. **CI 预合并检查**：PR 必须通过 `openspec validate`（对当前活跃 change）与项目自身测试，否则不允许合并。
6. **规格优先于对话**：当对话中的临时要求与已归档的 `openspec/specs/` 冲突时，先更新规格（走 change），再用新规格指导实现，不要静默偏离。

---

## 1. 什么是 OpenSpec

OpenSpec 是一个轻量、开源的**规格驱动开发框架**（来源：<https://openspec.dev>），专为 AI 编程助手设计，核心解决"需求只活在聊天记录里、AI 产出不可控"的问题。

- **无 API Key、极简安装**，以 Markdown 文件驱动，天然可被 AI 和人共同审查。
- **双目录模型**，把"当前事实"与"提案"分离：
  - `openspec/specs/`：系统当前事实（source of truth），按领域拆分。
  - `openspec/changes/`：待评审/进行中的变更提案，每个 change 自带 proposal、spec 增量、tasks。
- **变更闭环**：起草提案 → 评审对齐 → 实现 tasks → 归档合并。归档后增量规格回流进 `openspec/specs/`，成为下一个变更的基线。
- **AGENTS.md 兼容**：初始化后会写入 `openspec/AGENTS.md`，Claude Code / Cursor / CodeBuddy / Codex 等工具会自动读取并遵循 OpenSpec 工作流。

---

## 2. 环境要求与安装

- **Node.js ≥ 20.19.0**（当前环境已满足）
- 安装 CLI：

  ```bash
  npm install -g @fission-ai/openspec@latest
  openspec --version
  ```

- 在本仓库初始化（会提示选择你使用的 AI 工具，并生成 `openspec/` 目录、slash 命令与 `AGENTS.md`）：

  ```bash
  openspec init
  ```

- 切换工具或升级后，刷新 AI 指令与命令绑定：

  ```bash
  openspec update
  ```

---

## 3. 标准工作流（强制遵循）

| 阶段 | 动作 | 命令 / 指令 |
|---|---|---|
| 1. 起草提案 | 让 AI 创建 change 提案（proposal + spec 增量 + tasks） | `/openspec:proposal <描述>` 或 `/opsx:ff <描述>`（一次性生成） |
| 2. 评审对齐 | 评审并打磨规格，直到人机一致 | `openspec show <change>`、`openspec validate <change>` |
| 3. 实现 | 按 tasks 实现，逐项打勾 | `/openspec:apply <change>` 或 `/opsx:apply` |
| 4. 校验 | 归档前确认实现与规格一致 | `/opsx:verify` 或 `openspec status --change <change>` |
| 5. 归档 | 合并增量规格回源真相 | `/openspec:archive <change>` 或 `openspec archive <change> --yes` |

> 复杂/高风险变更建议用分步模式：`/opsx:new` → `/opsx:continue`（逐个产出 proposal / specs / design / tasks）→ 评审 → `/opsx:apply` → `/opsx:archive`。

---

## 4. 常用命令速查

```bash
openspec list                 # 列出活跃 change
openspec list --specs         # 列出源真相规格
openspec show <change>        # 查看某 change 的 proposal/tasks/spec 增量
openspec validate [<change>]  # 归档前校验结构与格式（CI 必跑）
openspec status --change <change>  # 查看 change 各产物进度
openspec archive <change> --yes    # 归档，合并增量规格
openspec view                 # 交互式仪表盘
openspec schemas              # 查看可选工作流 schema
openspec config profile       # 切换为分步（expanded）工作流
```

Slash 命令（Claude Code 原生）：`/openspec:proposal`、`/openspec:apply`、`/openspec:archive`；扩展族：`/opsx:explore`、`/opsx:ff`、`/opsx:new`、`/opsx:continue`、`/opsx:apply`、`/opsx:verify`、`/opsx:archive`、`/opsx:onboard`。

---

## 5. 规格增量格式（必须遵守）

- 用 `ADDED` / `MODIFIED` / `REMOVED` 标注变更类型。
- 需求标题用 `### Requirement:`，每条需求至少一个 `#### Scenario:` 场景块。
- 需求正文使用 **SHALL / MUST** 等强制措辞。

示例（change 内的 `specs/<domain>/spec.md`）：

```markdown
## ADDED Requirements

### Requirement: 行动前审计阻断旧版本
系统 MUST 在任务进入执行前校验其引用的参数版本是否为当前 active 版本。

#### Scenario: 引用已被替代的旧版本
- GIVEN 任务计划温度 80℃ 且当前有效主张为 70℃ v2（replaces 80℃ v1）
- WHEN 任务申请执行行动前审计
- THEN 审计结果 SHALL 为 `阻断` 并返回证据包与一键修正路径
```

---

## 6. 本项目的领域规格划分建议

`openspec/specs/` 按领域拆分（与 PRD 领域对象对齐），例如：

- `specs/meeting-ingest/`：妙记/事件接入、逐字稿、证据分段
- `specs/decision-compiler/`：Aily 决策编译、候选对象、语义分类
- `specs/decision-inbox/`：决策收件箱、三值留痕、发布闸门
- `specs/trust-rules/`：六道闸门、主张/参数/任务状态机、冲突检测
- `specs/action-audit/`：行动前审计五类检查、版本替代、一键修正
- `specs/result-backflow/`：结果回流、知识状态、失败边界卡
- `specs/contracts/`：`MeetingPackage` / `CandidatePackage` / `CardCallback` 接口契约（变更同样走 change）
  - **`FeishuActionRequest` 为历史备用契约**：平台→飞书反向联动的接口描述，新主路径（Aily 主动发卡）不依赖此项；保留作为历史参考。

> 两个子模块 `feishu-orchestrator` 与 `labmemory-platform` **共用仓库根 `openspec/`**，不要各自再建一套规格。

---

## 7. 与既有约定的关系

- **接口契约优先**：涉及 `contracts/` 的变更，先冻结契约再并行开发（见 README 第 5 节）。
- **数据口径诚实**：规格与评测中涉及指标时，必须标注"脱敏模拟/原型样例"，不得冒充真实企业收益。
- **保密**：本仓库为私有；规格中不得写入真实妙记、Token、受限文档等内容。
