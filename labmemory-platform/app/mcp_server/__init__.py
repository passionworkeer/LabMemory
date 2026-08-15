"""Aily MCP Server（同进程 SSE 暴露 10 个工具）。

入口在 `app.main::lifespan` 之后由 `app/mcp_server/transport.py::mount_mcp(app)`
挂载到 FastAPI；不挂载时（`MCP_ENABLED=false`）整个模块静默不可用。

调用关系：
    Aily（Host）──SSE──▶ /mcp/sse（sse-starlette）
                            └── POST /mcp/messages（SseServerTransport）
                                  └── mcp_server.call_tool()
                                        └── app/services/aily_helpers
                                              └── 既有领域逻辑
"""
from mcp.server import Server

mcp_server: Server = Server(
    name="labmemory",
    version="1.0.0",
    instructions=(
        "LabMemory 可信实验决策记忆系统。把飞书会议逐字稿编译为可审核、可版本化的"
        "实验决策；每条参数有证据、每次执行用对版本、每个结果反向校正知识。"
    ),
)

__all__ = ["mcp_server"]