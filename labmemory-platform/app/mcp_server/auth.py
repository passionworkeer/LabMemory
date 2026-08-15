"""MCP Server 鉴权：兼容 Bearer Header 与 URL queryParam。

设计依据（C1 修复 + Aily 接入现实）：
- Aily（飞书智能伙伴）后台「添加自定义 MCP」**只接受 name + url + desc**，
  无法配置 Authorization Header（一年多内部反馈未支持）
- 业界兼容做法（参考高德 MCP）：把鉴权 token 拼进 URL queryParam，
  `https://mcp.amap.com/sse?key=YOUR_KEY` — 服务端从 URL 取 token
- SSE 长连接的鉴权时机：只在 GET /mcp/sse 握手时校验一次；
  后续 POST /mcp/messages 由 MCP SDK 的 `_session_owners` 机制保证
  session 归属一致（同一 session 只能由创建它的认证身份发消息）
- MCP 协议层已经把这两个端点的归属绑死，本服务只关心 GET 鉴权，
  POST 端不需要再查 token（避免 Aily 后续 POST 时拿不到 token 失败）

设计原则：
- MCP 是**机器对机器**集成，由 Aily 调用，不是用户直接发起；
- user-level identity 在 UI 层处理：PI/Lead 通过登录 web 平台完成 decision verdict，
  executor 通过 web 提交执行结果；MCP 调用统一归属 Aily 系统账号
"""
from __future__ import annotations

import logging
from hmac import compare_digest

from fastapi import HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)


def _extract_token(request: Request) -> str | None:
    """按优先级取 token：Authorization Bearer > URL queryParam (?token= / ?key= / ?api_key=)。

    Aily 后台无法配 Header，所以 queryParam 是主路径；保留 Header 是为
    本地调试 / curl 自检 / 兼容未来 Aily 支持 Header 的可能性。
    """
    # 1) Authorization: Bearer <token>
    auth = request.headers.get("authorization")
    if auth:
        parts = auth.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            tok = parts[1].strip()
            if tok:
                return tok

    # 2) queryParam — 兼容多种命名（高德用 key、Aily 文档示例用 token）
    for name in ("token", "key", "api_key", "apikey"):
        v = request.query_params.get(name)
        if v:
            return v

    return None


def check_bearer(request: Request) -> None:
    """校验 MCP 请求鉴权（Header 或 queryParam）；失败抛 403。

    注：原计划复用 `verify_platform_api_key`，但其形参是 Header 依赖，需 FastAPI
    上下文；BaseHTTPMiddleware 中无依赖注入，必须手动取 token 后用 compare_digest
    比对（HMAC 防计时攻击）。
    """
    expected = settings.PLATFORM_API_KEY
    if not expected:
        logger.warning("MCP 鉴权失败：PLATFORM_API_KEY 未配置；path=%s", request.url.path)
        raise HTTPException(status_code=403, detail="server misconfigured: missing PLATFORM_API_KEY")

    token = _extract_token(request)
    if not token:
        logger.warning(
            "MCP 鉴权失败：缺少 token（Header Bearer 或 URL ?token=）；path=%s remote=%s",
            request.url.path,
            request.client.host if request.client else "?",
        )
        raise HTTPException(
            status_code=403,
            detail="missing token: provide Authorization Bearer header or URL queryParam ?token=<PLATFORM_API_KEY>",
        )

    if not compare_digest(token, expected):
        logger.warning(
            "MCP 鉴权失败：path=%s remote=%s token_prefix=%s",
            request.url.path,
            request.client.host if request.client else "?",
            token[:6] + "...",
        )
        raise HTTPException(status_code=403, detail="invalid token")


__all__ = ["check_bearer"]