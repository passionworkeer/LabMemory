"""MCP SSE 挂载到 FastAPI。

路径：
- GET  `{MCP_SSE_PATH}`        ← Aily 客户端入口（server→client SSE 流）
- POST `{MCP_MESSAGES_PATH}`   ← Aily 把 client→server 消息 POST 到这里
- GET  `/mcp/manifest`         ← 工具清单自检端点（接入调试用）

设计：
- 用 Starlette `Mount` 挂载一个独立 ASGI 子应用负责 /mcp/sse 和 /mcp/messages
- 该子应用持有 SseServerTransport 实例；
  GET 走 `connect_sse` 上下文后调用 `mcp_server.run()` 驱动消息泵
- DNS rebinding 保护显式关闭（生产由反向代理保证 Host/Origin 安全）
- 鉴权用 FastAPI 中间件，仅对 MCP 路径生效，避免 ASGI 子应用绕开
"""
from __future__ import annotations

import logging
from typing import Iterable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.sse import SseServerTransport
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.mcp_server import mcp_server
from app.mcp_server.auth import check_bearer
from app.mcp_server.tools import _tools_schema

logger = logging.getLogger(__name__)


# DNS rebinding 默认开启但 allowed_hosts=[]，会拒绝所有实际请求。
# H2/M1 修复：显式关闭 + 注释强化 — 生产环境 Host/Origin 校验责任在反向代理
# （Nginx `server_name` + `allow/deny` 指令，或 Cloudflare WAF），
# 平台侧不重复校验（避免 Aily 出口 Host 不在白名单内被误拒）。
# 文档：Aily 出口 IP 段须加入 Nginx allow 列表，详见 deploy/nginx-labmemory-mcp.conf。
_sse_transport = SseServerTransport(
    endpoint=settings.MCP_MESSAGES_PATH,
    security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


class _McpAuthMiddleware(BaseHTTPMiddleware):
    """所有 /mcp/* 请求先过 Bearer 鉴权（中间件层走，方便 ASGI 子应用也受保护）。

    中间件只能拦截 dispatch 链；ASGI 子应用走 Mount 直达，但本中间件顺序在外层，
    所以请求先经过中间件再决定是否进 Mount。
    """

    def __init__(self, app: ASGIApp, protected_prefixes: Iterable[str]):
        super().__init__(app)
        self._prefixes = tuple(protected_prefixes)

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self._prefixes):
            try:
                check_bearer(request)
            except Exception as exc:  # noqa: BLE001
                status_code = getattr(exc, "status_code", 403)
                detail = getattr(exc, "detail", "forbidden")
                return JSONResponse({"detail": detail}, status_code=status_code)
        return await call_next(request)


async def _mcp_sse_endpoint(scope: Scope, receive: Receive, send: Send) -> None:
    """GET /mcp/sse：建立 SSE 流并驱动 mcp_server.run()。

    鉴权已在中间件完成。connect_sse 上下文返回 (read_stream, write_stream)，
    然后 mcp_server.run() 在这两个流上循环处理 MCP 协议消息，
    直到客户端断开（http.disconnect 信号由 connect_sse 内部吞掉）。
    """
    if scope.get("type") != "http":
        return
    async with _sse_transport.connect_sse(scope, receive, send) as (read_stream, write_stream):
        await mcp_server.run(
            read_stream=read_stream,
            write_stream=write_stream,
            initialization_options=mcp_server.create_initialization_options(),
            raise_exceptions=False,
            stateless=True,
        )


async def _mcp_messages_endpoint(scope: Scope, receive: Receive, send: Send) -> None:
    """POST /mcp/messages：客户端→服务端消息回带。"""
    if scope.get("type") != "http":
        return
    await _sse_transport.handle_post_message(scope, receive, send)


async def _mcp_manifest_endpoint(request: Request) -> JSONResponse:
    """GET /mcp/manifest：导出工具清单（与 mcp_server.list_tools 一致）。

    M5 修复：经 Bearer 鉴权后暴露完整 inputSchema 给客户端。
    决策依据：MCP 协议本身就是「带 Bearer 的契约」，没有不暴露工具的方案；
    若 Bearer 泄漏，攻击者已知 MCP 集成关系，schema 暴露不构成新攻击面。
    描述字段含内部模型名（如 `labmemory_publish_knowledge`）是有意为之 —
    让 Aily 接入方在集成阶段知道工具能力边界，避免黑盒调用。
    """
    tools = _tools_schema()
    return JSONResponse(
        {
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
    )


def _build_mcp_subapp() -> ASGIApp:
    """把 MCP 三条路由组装为一个 Starlette 子应用，挂到 FastAPI /mcp 之下。

    注意：Starlette Mount 挂在 /mcp，子应用内 Route 路径要去掉 mount 前缀。
    """
    # MCP_SSE_PATH 默认 /mcp/sse，子应用里改成 /sse；其余同理
    sse_sub_path = settings.MCP_SSE_PATH.removeprefix("/mcp")  # /sse
    msg_sub_path = settings.MCP_MESSAGES_PATH.removeprefix("/mcp")  # /messages
    subapp = Starlette(
        routes=[
            Route(sse_sub_path, endpoint=_mcp_sse_endpoint, methods=["GET"]),
            Route(msg_sub_path, endpoint=_mcp_messages_endpoint, methods=["POST"]),
            Route("/manifest", endpoint=_mcp_manifest_endpoint, methods=["GET"]),
        ]
    )
    return subapp


def mount_mcp(app: FastAPI) -> None:
    """把 MCP SSE + Messages + Manifest 挂到 FastAPI；MCP_ENABLED=false 时静默跳过。

    H3 修复：检测三种"危险配置"并 fail-loud：
    1. APP_ENV != production 但 PLATFORM_API_KEY 是代码默认 sentinel
       （conftest 里 'dev-platform-api-key-please-rotate' / .env.example 同值）
       → 任何读到 .env.example 的人都拿到生产 Bearer
    2. PLATFORM_API_KEY 空或长度 < 32
    3. APP_ENV=development 时输出 warning（仍挂载，便于 dev 调试）
    """
    if not settings.MCP_ENABLED:
        logger.info("MCP 未启用（MCP_ENABLED=false），跳过挂载")
        return

    # H3 危险配置检测
    _default_sentinels = {
        "dev-platform-api-key-please-rotate",  # conftest 默认
        "change-me-in-production",  # 通用 sentinel
    }
    api_key = settings.PLATFORM_API_KEY or ""
    is_default_key = api_key in _default_sentinels
    is_short_key = len(api_key) < 32
    is_prod = settings.APP_ENV == "production"

    if is_prod and (is_default_key or is_short_key):
        logger.error(
            "MCP 拒绝挂载：APP_ENV=production 但 PLATFORM_API_KEY=%s；"
            "请在 .env 中覆盖为 ≥32 字节的强随机值",
            "默认值" if is_default_key else f"仅 {len(api_key)} 字节",
        )
        return
    if is_default_key:
        logger.warning(
            "⚠️ MCP 挂载但 PLATFORM_API_KEY 是代码默认 sentinel（%s）；"
            "生产环境必须覆盖，dev/测试环境可忽略",
            api_key[:12] + "...",
        )
    elif is_short_key:
        logger.warning("⚠️ MCP 挂载但 PLATFORM_API_KEY 仅 %d 字节（建议 ≥32）", len(api_key))
    if not is_prod:
        logger.info("MCP 挂载于非生产环境 APP_ENV=%s（debug/开发模式）", settings.APP_ENV)

    protected_prefixes = [settings.MCP_SSE_PATH, settings.MCP_MESSAGES_PATH, "/mcp/manifest"]
    app.add_middleware(_McpAuthMiddleware, protected_prefixes=protected_prefixes)

    subapp = _build_mcp_subapp()
    # 用 Starlette Mount 挂到 /mcp；Mount 内的路径要相对，比如 sse_path="/sse" 实际访问 /mcp/sse
    app.mount("/mcp", subapp)

    logger.info(
        "MCP 已挂载：%s (GET) / %s (POST) / /mcp/manifest (GET)",
        settings.MCP_SSE_PATH,
        settings.MCP_MESSAGES_PATH,
    )


__all__ = ["mount_mcp"]