"""飞书 UUAP / OAuth 免登客户端（网页应用登录）。

对接飞书开放平台「网页应用」OAuth 2.0（UUAP 统一认证免登）：

1. 生成授权 URL：``GET {FEISHU_OAUTH_AUTHORIZE_URL}?client_id=..&response_type=code&redirect_uri=..&state=..``
2. 授权后飞书回调 redirect_uri，携带 ``code`` + ``state``
3. ``exchange_code`` 用 code 换 ``user_access_token``（POST authen/v2/oauth/token）
4. ``fetch_user_info`` 用 token 取用户信息（name / open_id / union_id / email ...）

``FEISHU_OAUTH_MODE=mock`` 时不发起真实 HTTP（本地验证流程用），由 auth 端点
走 ``mock_profile`` 构造模拟用户。
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
import urllib.parse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# state 防 CSRF：内存存储，5 分钟过期（与飞书授权码有效期一致）
_STATE_TTL_SECONDS = 5 * 60
_states: dict[str, float] = {}
_states_lock = threading.Lock()


class FeishuOAuthError(Exception):
    """飞书 OAuth 交互失败（换 token / 取用户信息）。"""


def is_mock() -> bool:
    return settings.FEISHU_OAUTH_MODE != "real"


def new_state() -> str:
    """生成并登记一个授权 state（一次性，防 CSRF）。"""
    state = secrets.token_urlsafe(24)
    with _states_lock:
        _states[state] = time.monotonic()
    return state


def verify_state(state: str) -> bool:
    """校验并消费 state；失败/过期返回 False（一次性）。"""
    with _states_lock:
        ts = _states.pop(state, None)
    if ts is None:
        return False
    return (time.monotonic() - ts) <= _STATE_TTL_SECONDS


def build_authorize_url(state: str) -> str:
    """构造飞书授权页 URL（real 模式）。"""
    params = {
        "client_id": settings.FEISHU_OAUTH_APP_ID,
        "response_type": "code",
        "redirect_uri": settings.FEISHU_OAUTH_REDIRECT_URI,
        "state": state,
    }
    if settings.FEISHU_OAUTH_SCOPE:
        params["scope"] = settings.FEISHU_OAUTH_SCOPE
    qs = urllib.parse.urlencode(params)
    return f"{settings.FEISHU_OAUTH_AUTHORIZE_URL.rstrip('/')}?{qs}"


def exchange_code(code: str) -> str:
    """授权码换 user_access_token（POST authen/v2/oauth/token）。"""
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.FEISHU_OAUTH_APP_ID,
        "client_secret": settings.FEISHU_OAUTH_APP_SECRET,
        "code": code,
        "redirect_uri": settings.FEISHU_OAUTH_REDIRECT_URI,
    }
    try:
        resp = httpx.post(settings.FEISHU_OAUTH_TOKEN_URL, json=payload, timeout=10)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise FeishuOAuthError(f"飞书换 token 网络失败：{exc}") from exc
    if data.get("code") != 0 or not data.get("access_token"):
        raise FeishuOAuthError(
            "飞书换 token 失败："
            f"code={data.get('code')} error={data.get('error')} "
            f"desc={data.get('error_description')}"
        )
    return data["access_token"]


def fetch_user_info(user_access_token: str) -> dict:
    """用 user_access_token 获取用户信息。

    返回 dict 含 name / open_id / union_id / email / avatar_url / en_name 等。
    """
    try:
        resp = httpx.get(
            settings.FEISHU_OAUTH_USERINFO_URL,
            headers={"Authorization": f"Bearer {user_access_token}"},
            timeout=10,
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise FeishuOAuthError(f"飞书获取用户信息网络失败：{exc}") from exc
    if data.get("code") != 0:
        raise FeishuOAuthError(f"飞书获取用户信息失败：code={data.get('code')} msg={data.get('msg')}")
    return data.get("data") or {}


def mock_profile(user_key: str = "", display_name: str | None = None) -> dict:
    """mock 模式构造模拟飞书用户 profile（结构对齐 fetch_user_info 的 data）。"""
    key = user_key.strip() or f"u{secrets.token_hex(4)}"
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", key)[:40]
    name = (display_name or "").strip() or key
    return {
        "open_id": f"ou_mock_{slug}",
        "union_id": f"un_mock_{slug}",
        "name": name,
        "en_name": slug,
        "email": f"{slug}@feishu.example",
        "avatar_url": "",
    }
