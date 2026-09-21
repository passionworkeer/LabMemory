# 本地开发与调试指南 (Local Development Guide)

> 本文档为 LabMemory 本地环境搭建、前后端调试、自动化测试与 MCP 工具调优指南。

---

## 1. 环境准备

推荐操作系统：macOS 或 Linux (Ubuntu/Debian)。

| 软件 | 最低版本 | 推荐版本 | 说明 |
|---|---|---|---|
| Python | 3.12 | 3.12+ | 后端核心平台与编排器依赖 |
| uv | 0.4+ | 最新稳定版 | 极速 Python 包与虚拟环境管理 |
| Node.js | 20+ | 22 LTS | 前端构建与开发环境 |
| SQLite | 3.35+ | 3.45+ | 支持 JSON 与向量检索 |

---

## 2. 平台端 (labmemory-platform) 开发

### 2.1 依赖安装与虚拟环境
```bash
cd labmemory-platform

# 使用 uv 创建虚拟环境
uv venv
source .venv/bin/activate

# 安装生产与测试依赖
uv pip install -r requirements.txt
```

### 2.2 本地运行
```bash
# 拷贝开发环境变量
cp .env.example .env

# 启动开发服务器（带热重载，监听 127.0.0.1:8081）
uvicorn app.main:app --port 8081 --host 127.0.0.1 --reload
```

- Swagger UI API 文档：`http://127.0.0.1:8081/docs`
- 平台健康检查：`http://127.0.0.1:8081/health`
- MCP 工具清单（自检端点）：`http://127.0.0.1:8081/mcp/manifest`

### 2.3 运行后端测试套件
```bash
# 运行全部单元测试
pytest

# 仅跑快速冒烟测试
pytest tests/test_hardening_smoke.py -q
```

---

## 3. 前端界面 (frontend) 开发

前端基于 **React 19 + Vite + Tailwind CSS 4** 构建：

```bash
cd labmemory-platform/frontend

# 安装前端依赖
npm install

# 启动本地开发热重载（默认运行在 5173 端口，API 请求代理到 8081）
npm run dev

# 构建生产产物（产物将输出到 dist/，由 FastAPI 静态托管）
npm run build
```

---

## 4. 飞书编排器 (feishu-orchestrator) 调试

如果需要调试备用的飞书事件监听通道：

```bash
cd feishu-orchestrator/feishu-orchestrator

# 安装编排器依赖
pip install -r requirements.txt

# 运行编排器集成测试
python3 tests/test_integration.py
python3 tests/test_phase3.py

# 启动本地 Webhook 接收服务 (127.0.0.1:8080)
python3 -m core.webhook_server
```

---

## 5. MCP 本地自检与调试

MCP SSE 端点启动后，可通过 curl 模拟客户端建立连接并测试：

```bash
# 获取默认测试 API 凭据
export PLATFORM_API_KEY="dev-platform-api-key-please-rotate"

# 测试 SSE 握手与端点获取
curl -N -H "Authorization: Bearer $PLATFORM_API_KEY" http://127.0.0.1:8081/mcp/sse
```

更多 MCP 协议与飞书 Aily 联动规则详见 [AILY_MCP.md](../../AILY_MCP.md)。
