# LabMemory 晶研智流

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19.0+-61DAFB.svg?logo=react)](https://react.dev)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Standard-orange.svg)](https://modelcontextprotocol.io)
[![Lark / Feishu](https://img.shields.io/badge/Platform-Feishu%20%2F%20Lark-00D6B9.svg)](https://open.feishu.cn)

**嵌入飞书的可信实验决策与记忆系统**  
*让每条参数有证据，让每次执行用对版本，让每个结果反向校正知识。*

[特性亮点](#-特性亮点) • [系统架构](#-系统架构) • [快速开始](#-快速开始) • [文档地图](#-文档地图) • [开源协议](#-开源协议)

</div>

---

## 📖 项目简介

在生物医药、新材料与先进制造等研发实验室中，科学讨论通常发生在**飞书会议 / 妙记**中，而权威事实则记录在 **ELN / LIMS / 机器人控制台** 等垂直系统中。

**痛点在于**：
1. 会议讨论包含关键参数调整，但人工从数万字纪要中提取结论极易遗漏或产生理解偏差。
2. 传统大模型直接总结易产生幻觉，且缺乏科学验证责任人机制。
3. 旧版参数被废弃后，缺乏系统性拦截，导致实验室经常**误用已淘汰参数开展耗资巨大的重复实验**。
4. 实验失败结果只孤立沉淀在报告中，无法反向修正最初的理论假设。

**LabMemory（晶研智流）** 作为连接协同中枢（飞书）与实验室专业系统的**可信决策记忆与行动治理层**：
将自然语言科学研讨**编译**为可审核的结构化决策，用**实验护照**贯通全链路生命周期，并在执行前**自动阻断**过期或冲突参数，最终通过实验结果**反向校正**知识图谱。

---

## 🌟 特性亮点

### 1. 会议决策编译器 (Decision Compiler)
- 飞书妙记或会议纪要输入后，自动抽离出**候选参数、核心主张、支撑证据、争议风险与落地任务**。
- 候选值与原话精准锚定，模型生成内容打上置信度标记，进入决策收件箱待人工审核。

### 2. 可信实验记忆与六道质量闸门 (Trusted Decision Memory)
- 任何主张进入可信库前必须经过：**来源有效性、证据可复核性、版本链连续性、状态机合规性、适用范围约束、责任人背书** 六道闸门。
- 采用**三值留痕**机制：原始发言、模型提取值、人工核定值全程独立保留，审计路径不可篡改。

### 3. 实验护照贯通全生命周期 (Experiment Passport)
- 围绕实验编号（如 `EXP-DEMO-001`）构建统一档案，双向穿透：
  - 从“最终执行数据”可逆向追溯到“核准版本”与“会议逐字稿原话”；
  - 从“参数修订决策”可前向检索所有被影响的任务、派生实验与协同卡片。

### 4. 行动前审计五重检查 (Pre-action Audit)
- 在实验任务下发/执行前，自动运行五重防线：
  - 🛑 **版本替代检查**：拦截已淘汰参数版本（如阻断已废弃的 80℃ 参数，提示当前有效 70℃ 版本）；
  - 🛑 **争议未决检查**：拦截存在未决严重风险或争议的决策；
  - 🛑 **证据失效检查**：拦截依赖证据已被证伪或外链失效的主张；
  - 🛑 **前置依赖检查**：拦截前置工序未完成的任务；
  - 🛑 **参数越界检查**：拦截超出设备或工艺安全边界的配置。
- 输出 **通过 / 需确认 / 阻断** 三态判定，由 PI/实验主管在飞书互动卡片或控制台一键处置。

### 5. 结果反向校正与失败边界卡 (Closed-loop Backflow)
- 实验真实产出录入后，自动校正知识主张状态：`supported`（完全支持）、`refuted`（证伪反驳）、`partially_supported`（部分支持）。
- 异常或证伪时，自动生成**失败边界卡**（明确失败触发条件、排除机理、推荐下一步路线），并派生复验任务。

---

## 🏛️ 系统架构

系统包含两大接入途径与统一平台内核：

```
                             ┌───────────────────────────────────────┐
                             │       飞书协同中枢 (Lark / Feishu)      │
                             │  - 飞书妙记 (Minutes) / 视频会议       │
                             │  - 飞书互动卡片 / 任务 (Tasks) / 云文档  │
                             └──────────────────┬────────────────────┘
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼ (推荐主路径)                                                 ▼ (备用路径)
   ┌───────────────────────────┐                                 ┌───────────────────────────┐
   │     飞书 Aily Agent       │                                 │     feishu-orchestrator   │
   │  - 决策记忆 Skill (v1.0.8) │                                 │  - Webhook 事件接收服务器  │
   │  - 主动发卡与状态轮询       │                                 │  - 妙记/文档/任务 CLI 适配 │
   └─────────────┬─────────────┘                                 │  - 幂等防护与重试退避引擎 │
                 │                                               └─────────────┬─────────────┘
                 │ Model Context Protocol (MCP SSE)                            │ HTTP REST
                 │ 10 标准化工具:                                               │ 备用通道 (/v1/*)
                 │  - submit_transcript                                        │
                 │  - fetch_candidates                                         │
                 │  - confirm_claim                                            │
                 │  - audit_action                                             │
                 │  - ingest_result ...                                        │
                 ▼                                                             ▼
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 LabMemory Platform (核心平台)                               │
│                                                                                            │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌────────────────────────────────┐  │
│  │    决策收件箱 (Inbox)   │  │   实验护照 (Passport)  │  │      行动审计 (Audit Engine)  │  │
│  │  三值留痕 / 人工会签   │  │   全链路时序关系网络   │  │    五重闸门 / 实时拦截与建议  │  │
│  └───────────────────────┘  └───────────────────────┘  └────────────────────────────────┘  │
│                                                                                            │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌────────────────────────────────┐  │
│  │   可信问答 (RAG & QA)   │  │   状态机与数据模型     │  │   MCP Server (/mcp/sse)        │  │
│  │ 意图识别/混合检索/防幻觉│  │ 17 张核心表 / SQLite-vec │  │   工具派发 / 安全鉴权 / 审计   │  │
│  └───────────────────────┘  └───────────────────────┘  └────────────────────────────────┘  │
└──────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                               │
                                 ┌─────────────┴─────────────┐
                                 │    Web Frontend (前端)    │
                                 │ React 19 + Tailwind CSS 4 │
                                 │ 控制塔 / 收件箱 / 护照 / 问答│
                                 └───────────────────────────┘
```

---

## 📁 目录结构

```
LabMemory/
├── README.md                      # 项目入口与总览（本文档）
├── LICENSE                        # MIT 开源协议
├── CONTRIBUTING.md                 # 贡献指南
├── PROJECT_GUIDE.md               # 平台能力与架构设计总览
├── INTEGRATION.md                 # 双子系统联调与集成规范
├── AILY_MCP.md                    # 飞书 Aily MCP Server 协议规范与工具契约
├── AILY_INTEGRATION.md            # Aily 接口与出站 Webhook 规范
├── AUDIT.md                       # 对抗性审查与安全落地报告
├── CLAUDE.md                      # OpenSpec 开发与协作规范
├── sample_card.json               # 飞书互动卡片样例模板
│
├── labmemory-platform/            # 自研平台核心（FastAPI + React 19）
│   ├── app/                       # 后端核心源码（API、DB 模型、服务、MCP Server）
│   ├── frontend/                  # 前端源码（React 19 + Vite + Tailwind CSS 4）
│   ├── deploy/                    # Nginx 与 Cloudflare 反代配置片段
│   ├── tests/                     # 平台自动化测试套件
│   ├── pyproject.toml             # Python 项目声明
│   └── requirements.txt           # 核心依赖清单
│
├── feishu-orchestrator/           # 飞书侧编排子系统（备用路径）
│   └── feishu-orchestrator/       # Webhook 服务、Lark 适配器、可靠性引擎与集成测试
│
├── LabMemory 决策记忆/            # 飞书 Aily Skill 标准包（v1.0.8）
│   └── labmemory-decision-memory/ # Skill 提示词、卡片配置、状态轮询与工具映射
│
├── openspec/                      # OpenSpec 冻结规格与变更提案
│   ├── specs/                     # 13 个领域的系统源真相（Single Source of Truth）
│   └── changes/                   # 历史变更提案与归档记录
│
├── docs/                          # 详细开发、API 与运维文档
│   ├── README.md                  # 完整文档索引导航
│   ├── api-meetings-integration.md# REST API 接口契约
│   ├── infrastructure/            # 部署架构与 checklist
│   └── operations/                # 本地开发与运维 runbook
│
└── demo/                          # 演示工程与验证产物
    ├── LabMemory-Demo-V3-成片.mp4 # 演示成片视频（83s）
    ├── remotion/                  # Remotion 代码驱动视频工程源码
    └── scripts/                   # 媒体预处理与剪辑脚本
```

---

## 🚀 快速开始

### 1. 环境准备
- Python 3.12+
- Node.js 20+
- 推荐使用 [uv](https://github.com/astral-sh/uv) 管理 Python 虚拟环境与依赖。

### 2. 启动核心平台 (labmemory-platform)

```bash
cd labmemory-platform

# 1. 创建虚拟环境并安装依赖
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 按需编辑 .env（默认配置即可直接进行本地离线运行与测试）

# 3. 运行自动化测试确保环境就绪
pytest

# 4. 启动后端服务
uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

后端服务将在 `http://localhost:8081` 启动。
- API 文档可在 `http://localhost:8081/docs` 查看（开发环境）。
- MCP SSE 端点位于 `http://localhost:8081/mcp/sse?token=<PLATFORM_API_KEY>`。

### 3. 构建与运行前端 (frontend)

```bash
cd labmemory-platform/frontend

# 安装依赖
npm install

# 本地开发热重载
npm run dev

# 生产环境编译
npm run build
```

前端构建产物由 FastAPI 托管，直接访问 `http://localhost:8081` 即可体验。

### 4. 运行飞书编排器测试（可选）

```bash
cd feishu-orchestrator/feishu-orchestrator
python3 tests/test_integration.py
python3 tests/test_phase3.py
```

---

## 🔌 飞书 Aily MCP 对接

LabMemory 原生支持 **Anthropic Model Context Protocol (MCP)**。
通过同进程内挂载的标准 SSE 服务，飞书 Aily 智能体可直接作为 Host 调度 LabMemory 的 10 大可信能力：

| 工具名称 | 功能说明 |
|---|---|
| `submit_transcript` | 提交会议逐字稿或要点文本 |
| `fetch_candidates` | 查询编译生成的决策候选对象 |
| `create_review` | 发起决策人工复核流程并生成飞书会签卡片 |
| `confirm_claim` | 确认/修正决策参数并完成版本入库 |
| `audit_action` | 执行实验任务前的五项合规审计与冲突阻断 |
| `create_task` | 基于有效参数版本创建飞书待办任务 |
| `ingest_result` | 录入实验结果并反向校正知识状态 |
| `query_knowledge` | 检索可信实验知识库（含状态过滤与适用范围） |
| `get_experiment_passport`| 获取实验全生命周期护照档案 |
| `get_control_tower_summary`| 获取决策控制塔待办概览 |

详细接入步骤与卡片模板见 [AILY_MCP.md](AILY_MCP.md) 与 [LabMemory 决策记忆 Skill 包](LabMemory%20决策记忆/labmemory-decision-memory/SKILL.md)。

---

## 🔒 数据脱敏与合规声明

- 本仓库中包含的所有实验编号（如 `EXP-DEMO-001`）、工艺化合物名称、反应温度、催化剂配比及会议逐字稿文本**均为用于系统功能演示而人工合成的脱敏模拟数据**。
- 不代表任何商业公司或科研机构的真实业务机密与研发专利。
- 仓库代码与配置中已清除全部生产服务器凭据、私有秘钥、真实 IP 与私人联系方式。

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源协议。
欢迎任何形式的 Issue、Pull Request 与学术/工业界交流！
