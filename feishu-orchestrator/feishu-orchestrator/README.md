# LabMemory 飞书编排与 AI 接入子系统

> 负责把妙记、Aily、多维表格、交互卡片、任务和知识发布串成稳定链路，向自研 LabMemory 平台提供统一标准接口。

## 目录

- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [目录结构](#目录结构)
- [核心模块](#核心模块)
- [事件驱动架构](#事件驱动架构)
- [接口契约](#接口契约)
- [运行模式](#运行模式)
- [可靠性保障](#可靠性保障)
- [测试](#测试)
- [开发指南](#开发指南)
- [里程碑](#里程碑)
- [明确不做](#明确不做)

---

## 系统架构

### 主链路（9 步）

```
会议结束/妙记生成 → 事件去重与关联 → 获取逐字稿 → 组装 MeetingPackage
    → 调用 Aily 编译 → 校验 CandidatePackage → 推送至平台
    → 接收平台结果 → 发送卡片/创建任务/同步多维表格/发布知识文档
```

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        feishu-orchestrator                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐                                                │
│  │  Webhook     │ ← 飞书事件订阅 / 卡片回调                      │
│  │  Server      │                                                │
│  └──────┬───────┘                                                │
│         │                                                        │
│  ┌──────▼───────┐    ┌──────────┐    ┌──────────┐    ┌────────┐ │
│  │  Event       │───▶│ Meeting  │───▶│  Aily    │───▶│Platform│ │
│  │  Router      │    │ Package  │    │ Compiler │    │ Client │ │
│  └──────────────┘    │ Builder  │    └──────────┘    └───┬────┘ │
│                      └──────────┘                         │      │
│                                                           │      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │      │
│  │  Task    │◀───│  Card    │◀───│ Platform │◀────────────┘      │
│  │ Creator  │    │ Handler  │    │ Callback │                    │
│  └──────────┘    └──────────┘    └──────────┘                    │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                   │
│  │  Base    │    │  Docs    │    │  State   │                   │
│  │ Adapter  │    │ Adapter  │    │ Machine  │                   │
│  └──────────┘    └──────────┘    └──────────┘                   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Adapters Layer                       │    │
│  │  Minutes │ Aily │ Base │ IM Card │ Task │ Docs          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                   │
│  │  Idemp.  │    │  Retry   │    │  Logger  │                   │
│  │  Guard   │    │  Engine  │    │ (IntLog) │                   │
│  └──────────┘    └──────────┘    └──────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 环境准备

```bash
# 进入项目目录
cd feishu-orchestrator

# 安装依赖（当前仅依赖 Python 标准库）
python3 --version  # 需要 Python 3.8+
```

### 运行演示

```bash
# 🎯 统一演示入口（推荐，交互式菜单）
python scripts/demo_all.py

# 健康检查
python scripts/health_check.py

# 基础演示（妙记 → Aily 编译 → 平台提交 → 卡片通知）
python scripts/run_pipeline.py --demo

# 端到端演示（事件驱动 + 任务闭环）
python scripts/demo_end_to_end.py

# 异常场景演示（幂等、重试、延迟、阻断等 8 个场景）
python scripts/demo_exceptional_cases.py

# 🛠️ 管理控制台（人工兜底/重放/调试）
python scripts/admin_cli.py

# 重置演示环境
python scripts/demo_recovery.py
```

### 管理控制台功能

`python scripts/admin_cli.py` 提供交互式管理界面：

- 查看流程列表和详情
- 重放指定流程
- 手动触发流程（妙记链接 / 文本输入）
- 查看集成日志
- 查看状态机状态
- 查看多维表格台账
- 查看知识文档
- 重置演示环境

### 启动服务

```bash
# 启动 Webhook 事件接收服务
python -m core.webhook_server

# 启动 Mock Platform Server（供平台侧联调）
python -m mock.mock_server
```

### 运行测试

```bash
# 集成测试（Phase 1 + Phase 2）
python tests/test_integration.py

# Phase 3 单元测试
python tests/test_phase3.py
```

---

## 目录结构

```
feishu-orchestrator/
├── contracts/                    # 接口契约（与平台共享）
│   ├── meeting-package.schema.json      # MeetingPackage Schema
│   ├── candidate-package.schema.json    # CandidatePackage Schema
│   └── feishu-action-request.schema.json # 飞书动作请求 Schema
├── adapters/                     # 适配器层
│   ├── minutes_adapter.py              # 妙记读取适配器
│   ├── aily_adapter.py                 # Aily 决策编译适配器
│   ├── im_card_adapter.py              # 交互卡片适配器
│   ├── task_adapter.py                 # 飞书任务适配器
│   ├── base_adapter.py                 # 多维表格台账适配器
│   └── docs_adapter.py                 # 云文档知识发布适配器
├── core/                         # 核心业务逻辑
│   ├── config.py                       # 配置加载
│   ├── utils.py                        # 工具函数
│   ├── state_machine.py                # 状态机
│   ├── event_router.py                 # 事件路由
│   ├── webhook_server.py               # Webhook HTTP 服务
│   ├── platform_client.py              # 平台对接客户端
│   ├── card_handler.py                 # 卡片回调处理
│   └── pipeline_orchestrator.py        # 主编排器
├── reliability/                  # 可靠性保障
│   ├── integration_log.py              # 集成日志
│   ├── idempotency.py                  # 幂等控制
│   └── retry_engine.py                 # 重试引擎
├── mock/                         # Mock 数据和服务
│   ├── sample_aily_output.json         # 示例 Aily 输出
│   └── mock_server.py                  # Mock Platform Server
├── config/                       # 配置
│   └── env.example                   # 环境变量模板
├── scripts/                      # 脚本工具
│   ├── run_pipeline.py               # 一键跑通主链路
│   ├── demo_end_to_end.py            # 端到端完整演示
│   ├── demo_exceptional_cases.py     # 异常场景演示
│   ├── health_check.py               # 健康检查
│   └── demo_recovery.py              # 演示环境重置
├── tests/                        # 测试
│   ├── test_integration.py           # 集成测试套件
│   └── test_phase3.py                # Phase 3 单元测试
├── data/                         # 运行时数据（自动创建）
│   ├── state/                        # 状态机状态
│   ├── idempotency/                  # 幂等记录
│   └── integration_logs/             # 集成日志
├── logs/                         # 日志
└── README.md
```

---

## 核心模块

### 1. MinutesAdapter（妙记适配器）

**职责**：从飞书妙记获取逐字稿、说话人、时间戳、章节等信息

**功能**：
- 搜索妙记
- 获取妙记详情
- 通过 meeting_id 反查妙记
- 通过妙记链接获取
- 转换为标准 MeetingPackage

**使用方式**：
```python
from adapters.minutes_adapter import minutes_adapter

# 获取妙记详情
detail = minutes_adapter.get_by_url("https://.../minutes/xxx")

# 转换为 MeetingPackage
meeting_package = minutes_adapter.to_meeting_package(detail)
```

### 2. AilyAdapter（Aily 决策编译适配器）

**职责**：调用 Aily Skill 将会议自然语言编译为结构化候选决策

**功能**：
- 长会议分段处理（按章节，避免超长输入）
- 多段结果合并去重
- 规则二次校验（参数格式、必填字段）
- 多层容错 JSON 解析

**版本管理**：
- SKILL_VERSION: v1.0.0
- PROMPT_VERSION: v1.0.0
- MODEL_VERSION: default

**支持的候选类型**：
- `decision` - 决策
- `conclusion` - 结论
- `risk` - 风险
- `action_item` - 行动项
- `question` - 疑问
- `parameter_change` - 参数变更

**使用方式**：
```python
from adapters.aily_adapter import aily_adapter

candidate_package = aily_adapter.compile(meeting_package)
```

### 3. PlatformClient（平台对接客户端）

**职责**：与 LabMemory 平台的接口对接

**核心接口**：

| 接口 | 方向 | 说明 |
|------|------|------|
| POST /v1/candidates | 飞书 → 平台 | 提交 CandidatePackage |
| POST /v1/card/callback | 平台 ← 飞书 | 卡片回调转发 |
| POST /v1/task/status | 飞书 → 平台 | 任务创建状态回传 |
| GET /v1/candidates/{id} | 飞书 → 平台 | 获取候选详情 |

**使用方式**：
```python
from core.platform_client import platform_client

# 提交候选
result = platform_client.submit_candidates(candidate_package)

# 转发卡片回调
result = platform_client.forward_card_callback(callback_data)

# 更新任务状态
result = platform_client.update_task_status(candidate_id, task_guid, "success")
```

### 4. IMCardAdapter（交互卡片适配器）

**职责**：发送飞书交互卡片和处理回调

**卡片类型**：
- 📋 待复核卡片：候选决策摘要 + 「确认」「修正」「驳回」按钮
- ✅ 已批准卡片：生效通知 + 「查看详情」「打开任务」按钮
- 🚫 已阻断卡片：阻断原因 + 「查看详情」按钮
- ⚠️ 异常告警卡片：失败原因 + 「重试」按钮

**使用方式**：
```python
from adapters.im_card_adapter import im_card_adapter

# 发送待复核卡片
message_id = im_card_adapter.send_review_card(
    receive_id="user_xxx",
    candidate=candidate,
    meeting_title="会议标题",
    source_url="https://...",
)
```

### 5. TaskAdapter（飞书任务适配器）

**职责**：创建和管理飞书任务

**功能**：
- 从候选决策创建任务
- 获取任务详情
- 更新任务状态
- 自动构建任务描述（包含来源、证据、参数等）

**使用方式**：
```python
from adapters.task_adapter import task_adapter

task_guid = task_adapter.create_from_candidate(
    candidate=candidate,
    meeting_title="会议标题",
    source_url="https://...",
)
```

### 6. BaseAdapter（多维表格台账适配器）

**职责**：将候选决策同步到多维表格，便于批量查看和协作

**定位**：协作投影、批量查看、演示台账，不作为正式审批源

**功能**：
- 添加/更新记录
- 批量添加
- 按状态查询
- 更新任务链接

**表结构字段**：
候选ID、类型、标题、描述、来源会议、置信度、状态、关联实验、任务链接、平台详情、创建时间、更新时间

**使用方式**：
```python
from adapters.base_adapter import base_adapter

# 批量添加记录
record_ids = base_adapter.batch_add_records(candidates, "会议标题")

# 按状态查询
pending = base_adapter.list_records(status="pending_review")

# 更新任务链接
base_adapter.update_task_url(record_id, task_guid)
```

### 7. DocsAdapter（云文档知识发布适配器）

**职责**：将通过审核的决策发布为知识文档，沉淀团队经验

**文档类型**：
- ✅ **成功案例**：已验证成功的最佳实践
- ❌ **失败边界**：需要规避的失败案例
- ⏳ **待验证**：待进一步验证的结论

**文档内容结构**：
标题 + 类型说明 + 基本信息表 + 描述 + 参数变更 + 证据 + 自动生成标记

**使用方式**：
```python
from adapters.docs_adapter import docs_adapter

# 发布成功案例
result = docs_adapter.publish_success_case(candidate, "会议标题")

# 发布失败边界
result = docs_adapter.publish_failure_case(candidate, "会议标题", reason="风险过高")

# 发布待验证
result = docs_adapter.publish_pending_case(candidate, "会议标题")
```

### 8. StateMachine（状态机）

**职责**：管理会议/妙记的处理状态流转

**状态枚举**：
```
WAITING_MINUTES  → 会议已结束，等妙记
MINUTES_READY    → 妙记已就绪
COMPILING        → Aily 编译中
SUBMITTED        → 已提交平台
REVIEWING        → 复核中
APPROVED         → 已批准
COMPLETED        → 全链路完成
BLOCKED          → 已阻断
FAILED           → 失败
```

**使用方式**：
```python
from core.state_machine import state_machine, MeetingState

# 设置状态
state_machine.set_state("object_id", MeetingState.MINUTES_READY)

# 状态流转（带前置校验）
success = state_machine.transition(
    "object_id",
    from_state=MeetingState.MINUTES_READY,
    to_state=MeetingState.COMPILING,
)
```

### 9. EventRouter（事件路由器）

**职责**：统一事件入口，分发到对应处理器

**已注册事件**：

| 事件类型 | 处理器 | 说明 |
|---------|--------|------|
| `meeting.ended_v1` | handle_meeting_ended | 会议结束 |
| `minutes.minute.generated_v1` | handle_minutes_generated | 妙记生成 |
| `card.action_triggered` | handle_card_callback | 卡片回调 |

**功能**：
- 事件幂等检查（基于 event_id）
- 自动路由到对应处理器
- 状态机状态更新
- 集成日志记录

**使用方式**：
```python
from core.event_router import event_router

# 处理事件
result = event_router.handle_event({
    "type": "meeting.ended_v1",
    "event_id": "evt_001",
    "meeting_id": "meeting_001",
    "title": "测试会议",
})
```

### 10. CardHandler（卡片回调处理器）

**职责**：处理交互卡片的用户操作回调

**处理流程**：
```
收到回调 → 幂等检查 → 转发到平台 → 根据平台结果执行动作
    → approved: 创建任务 → 回写平台 → 发送已批准卡片
    → rejected: 发送已驳回通知
    → blocked: 发送阻断通知
```

**支持的操作**：
- `approved` / `approve` - 确认通过
- `rejected` / `reject` - 驳回
- `revise` / `pending_revision` - 待修改

**使用方式**：
```python
from core.card_handler import card_handler

result = card_handler.handle_callback({
    "token": "callback_001",
    "open_id": "user_xxx",
    "action": {
        "value": {
            "action_type": "approved",
            "candidate_id": "cand_001",
        }
    }
})
```

### 11. PipelineOrchestrator（主编排器）

**职责**：串联整个主链路

**入口方法**：
- `run_from_minutes_url(url, reviewer_id)` - 从妙记链接运行
- `run_from_minutes_token(token, reviewer_id)` - 从 minute_token 运行
- `run_from_text(text, title, reviewer_id)` - 从纯文本运行（人工兜底）

**使用方式**：
```python
from core.pipeline_orchestrator import pipeline_orchestrator

result = pipeline_orchestrator.run_from_minutes_url(
    minutes_url="https://...",
    reviewer_id="user_xxx",
)
```

### 12. WebhookServer（Webhook 服务）

**职责**：接收飞书事件订阅和卡片回调的 HTTP 请求

**端点**：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/webhook/event` | POST | 接收飞书事件订阅（v2.0 格式） |
| `/webhook/card` | POST | 接收交互卡片回调 |
| `/health` | GET | 健康检查 |

**功能**：
- URL 验证（challenge 响应）
- 签名验证（HMAC-SHA256）
- 请求体解析
- 路由到 EventRouter
- 入站集成日志

**启动方式**：
```bash
python -m core.webhook_server
# 或自定义端口
PORT=9000 python -m core.webhook_server
```

---

## 事件驱动架构

### 完整事件驱动流程

```
1. 会议结束
   ↓ (飞书事件)
2. WebhookServer 接收事件
   ↓
3. EventRouter 路由 + 幂等检查
   ↓
4. 状态机: WAITING_MINUTES
   ↓ (等待妙记生成)
5. 妙记生成事件到达
   ↓
6. 状态机: MINUTES_READY
   ↓ (触发编译)
7. Aily 编译 → CandidatePackage
   ↓
8. 提交到平台
   ↓
9. 状态机: SUBMITTED → REVIEWING
   ↓
10. 发送复核卡片
    ↓ (用户点击按钮)
11. 卡片回调到达
    ↓
12. CardHandler 处理
    ↓
13. 转发到平台审核
    ↓
14. 平台返回 approved
    ↓
15. 创建飞书任务
    ↓
16. 回写平台任务状态
    ↓
17. 状态机: APPROVED → COMPLETED
    ↓
18. 发送已批准卡片
```

---

## 接口契约

### MeetingPackage（会议数据包）

从妙记/会议转换而来的标准化数据结构，作为 Aily 编译的输入。

**核心字段**：
- `schema_version`: 版本号
- `source`: 来源（feishu_minutes / manual_upload / meeting_transcript）
- `source_object_id`: 来源对象 ID
- `meeting_id`: 会议 ID
- `title`: 会议标题
- `start_time` / `end_time`: 开始/结束时间
- `organizer`: 组织者
- `participants`: 参会人列表
- `content.transcript`: 逐字稿（speaker, start_offset_sec, end_offset_sec, text）
- `content.chapters`: 章节
- `content.summary`: 摘要
- `content.action_items`: 行动项
- `source_url`: 来源链接
- `captured_at`: 采集时间

### CandidatePackage（候选决策包）

Aily 编译输出的结构化候选决策，提交给平台审核。

**核心字段**：
- `schema_version`: 版本号
- `source_package_id`: 来源包 ID
- `aily_skill_version` / `model_version` / `prompt_version`: 版本信息
- `input_hash`: 输入哈希（用于幂等）
- `candidates[]`: 候选决策列表
  - `candidate_id`: 候选 ID
  - `type`: 类型（decision / conclusion / risk / action_item / question / parameter_change）
  - `title` / `description`: 标题/描述
  - `experiment_ref`: 关联实验
  - `parameters[]`: 参数变更
  - `confidence`: 置信度（0-1）
  - `evidence[]`: 证据（说话人、时间、原文、链接）
  - `status`: 状态
  - `needs_review`: 是否需要复核
  - `assignee` / `due_date`: 负责人/截止日期
- `risks[]`: 风险列表
- `action_items[]`: 行动项列表
- `open_questions[]`: 待澄清问题
- `compiled_at`: 编译时间
- `raw_output`: 原始输出（调试用）

### FeishuActionRequest（飞书动作请求）

平台向飞书侧发起的协作动作请求。

**核心字段**：
- `action_type`: 动作类型（send_card / create_task / update_base / publish_doc / notify）
- `candidate_id`: 关联候选 ID
- `payload`: 动作参数
- `request_id`: 请求 ID（幂等用）

---

## 运行模式

### Mock 模式（默认）

所有外部调用使用 Mock 实现，无需真实凭证，方便开发和演示。

```bash
# 默认就是 mock 模式
python scripts/run_pipeline.py --demo

# 或显式指定
RUN_MODE=mock python scripts/health_check.py
```

**Mock 数据特点**：
- 内置示例妙记（实验方案评审会）
- 基于规则的 Aily 编译（关键词识别）
- 内存状态的平台模拟
- 模拟任务创建（生成 task_xxx 格式的 GUID）

### Real 模式

调用真实的飞书 API 和 Aily 服务，需要配置凭证。

```bash
# 复制配置模板
cp config/env.example .env

# 编辑 .env，填入：
# - FEISHU_APP_ID / FEISHU_APP_SECRET
# - FEISHU_TENANT_ACCESS_TOKEN / FEISHU_USER_ACCESS_TOKEN
# - AILY_API_BASE / AILY_SKILL_ID / AILY_API_KEY
# - PLATFORM_API_BASE / PLATFORM_API_KEY
# - RUN_MODE=real

# 运行
python scripts/run_pipeline.py --minutes-url <妙记链接>
```

---

## 可靠性保障

### 1. 幂等控制（IdempotencyGuard）

**设计**：
- 幂等键：source_object_id + event_type + version
- 使用 MD5 哈希作为文件名
- 默认 TTL 7 天
- 存储在 `data/idempotency/` 目录

**应用场景**：
- 重复事件不重复编译
- 卡片回调不重复处理
- 任务不重复创建

### 2. 重试引擎（RetryEngine）

**重试策略**：
- 指数退避：base_delay * (backoff_factor ^ attempt)
- 最大延迟：60 秒
- 随机抖动：0.5~1.0 倍
- 默认最大重试次数：5 次

**可重试异常**：
- RetryableError、TimeoutError、ConnectionError
- 飞书限流错误（9999999、rate limit）
- 网络相关错误（timeout、connection、502、503、504）

**使用方式**：
```python
from reliability.retry_engine import with_retry

@with_retry(interface_name="my_api")
def my_function():
    ...
```

### 3. 集成日志（IntegrationLog）

**记录内容**：
- 调用时间、方向（inbound/outbound）、接口名
- 输入参数（自动脱敏）
- 输出结果/错误信息
- 耗时、状态、请求 ID

**存储**：按天 JSONL 文件（`data/integration_logs/`）

**自动脱敏**：token、secret、password、api_key、access_token 等字段

**用途**：问题排查、审计、重放

### 4. 状态机

- 明确的状态定义和流转规则
- 完整的状态流转历史
- 支持按状态查询和统计
- 处理延迟和异步场景

### 5. 多维表格台账

- 所有候选决策自动同步到多维表格
- 支持按状态、类型筛选
- 便于批量查看和协作
- 演示和汇报的好帮手

### 6. 知识发布

- 通过审核的决策自动发布为知识文档
- 结构化内容，便于阅读和检索
- 沉淀团队经验，避免重复踩坑

---

## 测试

### 集成测试（Phase 1 + Phase 2）

```bash
python tests/test_integration.py
```

覆盖 6 个测试类，15 个测试用例：
- TestEventDrivenFlow（3个）：会议结束事件、妙记生成事件、事件幂等性
- TestAilyCompiler（2个）：从妙记编译、从文本编译
- TestPlatformIntegration（3个）：提交候选、卡片回调通过、更新任务状态
- TestCardHandler（2个）：通过后创建任务、回调幂等性
- TestReliability（3个）：幂等守卫、集成日志、状态机流转
- TestPipelineOrchestrator（2个）：从妙记URL运行、从文本运行

### Phase 3 单元测试

```bash
python tests/test_phase3.py
```

覆盖 3 个测试类，19 个测试用例：
- TestBaseAdapter（6个）：添加、更新、批量添加、查询、类型标签
- TestDocsAdapter（5个）：成功案例、失败边界、待验证、内容生成、列表查询
- TestMockPlatform（8个）：提交、回调（通过/驳回/阻断）、任务更新、状态摘要、重置、规范化

### 健康检查

```bash
python scripts/health_check.py
```

检查 11 项核心模块是否正常：
- 配置加载
- 妙记适配器
- Aily 适配器
- 平台客户端
- 交互卡片
- 任务适配器
- 状态机
- 幂等控制
- 集成日志
- 重试引擎
- 主编排器

---

## 开发指南

### 新增适配器

1. 在 `adapters/` 目录下创建新的适配器文件
2. 实现 `__init__` 方法，支持 mock/real 双模式
3. 公共方法添加 `@with_retry` 装饰器
4. 添加集成日志记录
5. 在 `adapters/__init__.py` 中导出单例

### 新增事件类型

1. 在 `core/event_router.py` 中注册新的事件类型和处理函数
2. 处理函数中添加幂等检查
3. 更新状态机状态
4. 在测试中添加对应测试用例

### 新增可靠性机制

1. 在 `reliability/` 目录下创建新模块
2. 设计清晰的接口
3. 在核心模块中集成
4. 添加测试用例

### Mock Server 联调

启动 Mock Platform Server：
```bash
python -m mock.mock_server 8081
```

设置环境变量：
```bash
export PLATFORM_API_BASE=http://localhost:8081
export PLATFORM_API_KEY=mock-key
```

然后运行飞书编排系统即可与 Mock Server 联调。

**Mock Server 接口**：
- `GET /health` - 健康检查
- `POST /api/v1/candidates` - 提交候选
- `POST /api/v1/card/callback` - 卡片回调
- `POST /api/v1/task/status` - 任务状态更新
- `GET /api/v1/candidates/{id}` - 获取候选详情
- `GET /api/v1/mock/state` - 状态摘要
- `GET /api/v1/mock/state/detail` - 状态详情
- `POST /api/v1/mock/reset` - 重置状态

---

## 里程碑

### Phase 1：最小可用闭环 ✅

**目标**：跑通「人工输入妙记 → Aily 编译 → 提交平台 → 卡片通知」主链路

- [x] 搭建项目骨架 + 环境配置
- [x] 实现 MinutesAdapter（人工输入链接）
- [x] 实现 AilyAdapter（基础 Skill）
- [x] 实现 PlatformClient（提交接口）
- [x] 实现 IM Card 发送
- [x] 实现基础幂等 + 日志
- [x] 一键跑通脚本
- [x] 健康检查脚本
- [x] 演示恢复脚本
- [x] README 文档

**验收**：人工输入一个妙记链接，能自动生成候选决策并发送复核卡片

### Phase 2：事件驱动 + 任务闭环 ✅

**目标**：全自动事件触发 + 审批后创建任务

- [x] 接入妙记生成事件订阅（事件路由框架）
- [x] 实现会议-妙记关联状态机
- [x] 实现卡片回调处理
- [x] 实现 TaskAdapter
- [x] 实现任务状态回写
- [x] 完善重试机制
- [x] Webhook 事件接收服务
- [x] 端到端演示脚本
- [x] 集成测试用例（15个全部通过）
- [x] 修复 PlatformClient mock 的状态管理问题
- [x] 更新 README 和文档

**验收**：
- 健康检查：11/11 ✅
- 集成测试：15/15 ✅
- 端到端演示：7 步完整跑通，任务闭环 ✅

### Phase 3：完善与加固 🚧

**目标**：生产级可靠性 + 完整演示能力

- [x] 多维表格台账（BaseAdapter）
- [x] 知识发布（DocsAdapter）
- [x] Mock Server（供平台侧联调）
- [x] 异常场景演示脚本（8 个场景）
- [x] Phase 3 单元测试（19 个全部通过）
- [x] 人工兜底/重放界面（管理 CLI）
- [x] 部署文档 + 演示脚本完善
- [ ] 更多异常演示案例

**当前状态**：
- 健康检查：11/11 ✅
- 集成测试：15/15 ✅
- Phase 3 单元测试：19/19 ✅
- 异常场景演示：8/8 ✅
- 管理 CLI：10 个功能菜单 ✅
- 部署文档：完整的 DEPLOYMENT.md ✅

---

## 明确不做

- 不负责平台核心 UI、实验护照、版本图谱和业务状态机
- 不让 Aily 直接修改正式参数、批准实验或覆盖历史版本
- 不依赖当前租户尚不可用的多维表格记录变更事件
- 不为展示飞书能力而接入企业豆包、妙搭等与主链路无关的模块
- 不把 lark-cli 命令散落到业务代码；CLI 只作为适配器实现或开发验证工具
