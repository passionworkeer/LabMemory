"""Aily 接入清单静态导出（CI / 接入预审用）。

`transport.py::/mcp/manifest` 暴露运行时版（更实时）；
本文件导出**静态 JSON**，便于：
- CI 在 PR 上校验工具清单是否变更
- Aily 接入方在没有起 server 时拉一份样例
- 文档构建时把 manifest 渲染进 skill-prompt

用法：
    python -m app.mcp_server.manifest > tools-manifest.json
"""
from __future__ import annotations

import json

from app.config import settings
from app.mcp_server import mcp_server
from app.mcp_server.tools import _tools_schema


def build_manifest() -> dict:
    """构造 10 工具的清单 dict，与运行时 /mcp/manifest 保持一致。"""
    tools = _tools_schema()
    return {
        "server": {"name": mcp_server.name, "version": "1.0.0"},
        "transport": "sse",
        "sse_path": settings.MCP_SSE_PATH,
        "messages_path": settings.MCP_MESSAGES_PATH,
        "auth": "Bearer <PLATFORM_API_KEY>",
        "tools": [
            {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
            for t in tools
        ],
    }


def main() -> None:
    """CLI 入口：导出 JSON 到 stdout。"""
    print(json.dumps(build_manifest(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


__all__ = ["build_manifest"]