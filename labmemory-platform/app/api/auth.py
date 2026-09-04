"""登录与当前用户。"""
from __future__ import annotations

import base64
import json
import logging
import re
import secrets
import threading
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.core.errors import DomainError, PermissionDeniedError
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.schemas import FeishuAuthorizeOut, FeishuMockLoginIn, LoginIn, LoginOut, UserOut
from app.services import uuap_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 登录限速：同一 (用户名, IP) 连续失败达到阈值后锁定一段时间（防口令爆破）
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 15 * 60

_login_failures: dict[tuple[str, str], list[float]] = {}
_login_lock: threading.Lock = threading.Lock()


class LoginRateLimitedError(DomainError):
    status_code = 429
    code = "login_rate_limited"


def _client_ip(request: Request) -> str:
    """取客户端 IP（反向代理场景取 X-Forwarded-For 末段——由 nginx 追加的真实直连 IP，
    首段可被客户端伪造轮换，用于限速会被绕过）。"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _is_locked(username: str, ip: str, now: float) -> bool:
    cutoff = now - LOGIN_LOCK_SECONDS
    with _login_lock:
        fails = [t for t in _login_failures.get((username, ip), []) if t > cutoff]
        _login_failures[(username, ip)] = fails
        return len(fails) >= LOGIN_MAX_FAILURES


def _record_failure(username: str, ip: str, now: float) -> None:
    cutoff = now - LOGIN_LOCK_SECONDS
    with _login_lock:
        fails = [t for t in _login_failures.get((username, ip), []) if t > cutoff]
        fails.append(now)
        _login_failures[(username, ip)] = fails


def _clear_failures(username: str, ip: str) -> None:
    with _login_lock:
        _login_failures.pop((username, ip), None)


@router.post("/login", response_model=LoginOut)
def login(
    payload: LoginIn,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginOut:
    if not settings.PASSWORD_LOGIN_ENABLED:
        raise PermissionDeniedError("密码登录已关闭，请使用飞书登录")
    ip = _client_ip(request)
    now = time.monotonic()
    if _is_locked(payload.username, ip, now):
        raise LoginRateLimitedError("失败次数过多，账号已临时锁定，请 15 分钟后重试")
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        _record_failure(payload.username, ip, now)
        raise PermissionDeniedError("用户名或密码错误")
    _clear_failures(payload.username, ip)
    token = create_access_token(user.id, user.username, user.global_role)
    return LoginOut(access_token=token, user=UserOut.model_validate(user, from_attributes=True))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


# === 飞书 UUAP / OAuth 免登 ===

@router.get("/feishu/authorize", response_model=FeishuAuthorizeOut)
def feishu_authorize() -> FeishuAuthorizeOut:
    """登录页初始化：返回登录方式（real 跳转飞书 / mock 模拟 / 密码登录开关）。"""
    if uuap_client.is_mock():
        return FeishuAuthorizeOut(
            mode="mock",
            authorize_url=None,
            mock_enabled=True,
            password_login_enabled=settings.PASSWORD_LOGIN_ENABLED,
        )
    state = uuap_client.new_state()
    return FeishuAuthorizeOut(
        mode="real",
        authorize_url=uuap_client.build_authorize_url(state),
        mock_enabled=False,
        password_login_enabled=settings.PASSWORD_LOGIN_ENABLED,
    )


@router.get("/feishu/callback")
def feishu_callback(
    code: str = "",
    state: str = "",
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """飞书授权回调：换 token -> 取用户信息 -> 自动注册/登录 -> 重定向前端。

    mock 模式：``code`` 直接视为模拟用户 key，跳过真实飞书交互。
    """
    if error:
        return RedirectResponse("/login?error=" + quote("飞书授权未完成"), status_code=302)
    if not uuap_client.verify_state(state):
        return RedirectResponse("/login?error=" + quote("登录状态校验失败，请重新发起登录"), status_code=302)
    try:
        if uuap_client.is_mock():
            profile = uuap_client.mock_profile(code)
        else:
            access_token = uuap_client.exchange_code(code)
            profile = uuap_client.fetch_user_info(access_token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("飞书登录回调失败：%s", exc)
        return RedirectResponse("/login?error=" + quote(f"登录失败：{exc}"), status_code=302)
    user = _get_or_create_user(db, profile)
    token = create_access_token(user.id, user.username, user.global_role)
    # ensure_ascii=True：user JSON 转成纯 ASCII（\uXXXX），避免 base64 回调链路上的中文乱码
    user_b64 = base64.urlsafe_b64encode(
        json.dumps(
            UserOut.model_validate(user, from_attributes=True).model_dump(),
            ensure_ascii=True,
        ).encode("utf-8")
    ).decode("ascii")
    return RedirectResponse(f"/login?token={token}&user={user_b64}", status_code=302)


@router.post("/feishu/mock-login", response_model=LoginOut)
def feishu_mock_login(payload: FeishuMockLoginIn, db: Session = Depends(get_db)) -> LoginOut:
    """mock 模式模拟飞书免登（本地/演示验证自动注册流程）。"""
    if not uuap_client.is_mock():
        raise PermissionDeniedError("当前为 real 模式，模拟登录不可用")
    profile = uuap_client.mock_profile(payload.user_key, payload.display_name)
    user = _get_or_create_user(db, profile)
    token = create_access_token(user.id, user.username, user.global_role)
    return LoginOut(access_token=token, user=UserOut.model_validate(user, from_attributes=True))


def _get_or_create_user(db: Session, profile: dict) -> User:
    """UUAP 免登自动注册：按 open_id/union_id 查用户，不存在则创建（默认最低权限 viewer）。"""
    open_id = profile.get("open_id") or ""
    union_id = profile.get("union_id") or ""
    name = (profile.get("name") or profile.get("en_name") or "").strip() or open_id or "飞书用户"
    user = None
    if open_id:
        user = db.query(User).filter(User.feishu_user_id == open_id).first()
    if user is None and union_id:
        user = db.query(User).filter(User.feishu_user_id == union_id).first()
    if user is not None:
        return user
    user = User(
        username=_unique_username(db, profile),
        password_hash=secrets.token_urlsafe(32),  # 占位口令，密码登录不可用
        display_name=name[:128],
        feishu_user_id=open_id or union_id or None,
        global_role=settings.UUAP_AUTO_REGISTER_ROLE,
        source="feishu_auto",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("UUAP 自动注册新用户：username=%s global_role=%s", user.username, user.global_role)
    return user


def _unique_username(db: Session, profile: dict) -> str:
    """由 email 前缀 / open_id 后缀生成唯一用户名（fs_ 前缀，区分演示账号）。"""
    email = profile.get("email") or ""
    base = email.split("@")[0].strip() if email else ""
    if not base:
        base = "fs_" + (profile.get("open_id") or profile.get("union_id") or "")[-12:]
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", base).strip("._") or "fs_user"
    if not base.startswith("fs_"):
        base = "fs_" + base
    candidate = base[:60]
    seq = 1
    while db.query(User).filter(User.username == candidate).first():
        seq += 1
        candidate = f"{base[:56]}_{seq}"
    return candidate
