"""MCP Server 鉴权：仅 Bearer Token。

设计原则（C1 修复）：
- MCP 是**机器对机器**集成，由 Aily（飞书智能伙伴）调用，不是用户直接发起；
- user-level identity（MCP 调用的"谁"）应在 UI 层处理：PI/Lead 通过登录 web 平台
  完成 decision verdict，executor 通过 web 提交执行结果；MCP 调用统一归属 Aily
  系统账号（system actor），由 Aily 链路负责 UI 层用户映射与审计
- 因此 `x-aily-user` 头、Aily 出口 IP 白名单、MCP_ALLOW_INSECURE_USER_HEADER
  都是不必要的复杂化 — 直接删除，避免「声明了但未启用」的 trust boundary 漏洞
- 业务异常（NotFoundError / StateTransitionError）由 tools.to_call_result 翻译为
  CallToolResult(isError=True)，本层不参与身份解析
"""
from __future__ import annotations

import logging
from hmac import compare_digest

from fastapi import HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)


def check_bearer(request: Request) -> None:
    """校验 MCP 请求 Bearer；失败抛 403。

    注：原计划复用 `verify_platform_api_key`，但其形参是 Header 依赖，需 FastAPI
    上下文；BaseHTTPMiddleware 中无依赖注入，必须手动取 header 后用 compare_digest
    比对（HMAC 防计时攻击）。
    """
    auth = request.headers.get("authorization")
    expected = settings.PLATFORM_API_KEY
    if not auth or not expected:
        logger.warning("MCP 鉴权失败：缺少 Authorization/PLATFORM_API_KEY；path=%s", request.url.path)
        raise HTTPException(status_code=403, detail="missing bearer token")
    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=403, detail="malformed authorization header")
    token = parts[1].strip()
    if not compare_digest(token, expected):
        logger.warning(
            "MCP 鉴权失败：path=%s remote=%s token_prefix=%s",
            request.url.path,
            request.client.host if request.client else "?",
            token[:6] + "...",
        )
        raise HTTPException(status_code=403, detail="invalid bearer token")


__all__ = ["check_bearer"]