"""登录与当前用户。"""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import DomainError, PermissionDeniedError
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.schemas import LoginIn, LoginOut, UserOut

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
