"""FastAPI 依赖：DB 会话 + 当前用户 + 角色校验。"""
from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError
from app.core.security import decode_access_token
from app.db.models import Experiment, ExperimentMember, User
from app.db.session import get_db


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise PermissionDeniedError("缺少 Authorization Bearer 头")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except Exception as exc:  # noqa: BLE001
        raise PermissionDeniedError(f"无效的 JWT：{exc}") from exc
    user_id = int(payload.get("sub", "0"))
    user = db.get(User, user_id)
    if user is None:
        raise PermissionDeniedError("用户不存在")
    return user


def require_pi(user: User = Depends(get_current_user)) -> User:
    """仅项目负责人（PI）可访问。"""
    if user.global_role != "pi" and user.global_role != "admin":
        raise PermissionDeniedError("仅项目负责人（PI）可执行此操作")
    return user


def require_pi_or_lead(user: User = Depends(get_current_user)) -> User:
    """PI 或 Lead 可访问（用于发布知识等）。"""
    if user.global_role not in ("pi", "lead", "admin"):
        raise PermissionDeniedError("仅 PI 或 Lead 可执行此操作")
    return user


def require_member(user: User = Depends(get_current_user)) -> User:
    """PI / Lead / Executor 三类角色均可。"""
    if user.global_role not in ("pi", "lead", "executor", "admin"):
        raise PermissionDeniedError("无操作权限")
    return user


def get_experiment_or_404(db: Session, experiment_id: str) -> Experiment:
    exp = db.query(Experiment).filter(Experiment.experiment_id == experiment_id).first()
    if exp is None:
        from app.core.errors import NotFoundError
        raise NotFoundError(f"实验不存在：{experiment_id}")
    return exp


def ensure_experiment_member(db: Session, experiment_id: int, user: User) -> ExperimentMember:
    """校验用户是实验成员并返回成员关系；PI 全局角色自动视为成员。"""
    if user.global_role == "admin":
        m = db.query(ExperimentMember).filter(
            ExperimentMember.experiment_id == experiment_id,
            ExperimentMember.user_id == user.id,
        ).first()
        return m or ExperimentMember(experiment_id=experiment_id, user_id=user.id, role="pi")
    m = db.query(ExperimentMember).filter(
        ExperimentMember.experiment_id == experiment_id,
        ExperimentMember.user_id == user.id,
    ).first()
    if m is None:
        raise PermissionDeniedError("您不是该实验的成员")
    return m


def visible_experiment_ids(db: Session, user: User) -> set[int] | None:
    """返回用户可见的 experiment_id 集合；None 表示全局可见（admin）。"""
    if user.global_role == "admin":
        return None
    rows = db.query(ExperimentMember.experiment_id).filter(
        ExperimentMember.user_id == user.id
    ).all()
    return {r[0] for r in rows}


def verify_platform_api_key(
    authorization: str | None = Header(default=None),
    x_platform_api_key: str | None = Header(default=None),
):
    """飞书编排器调用 /api/v1/* 接口的鉴权。

    契约要求 Authorization: Bearer {PLATFORM_API_KEY}（contracts/spec.md:56-57）；
    为兼容平台既有测试夹具（X-Platform-Api-Key），双接受。
    """
    from app.config import settings
    from app.core.errors import PermissionDeniedError
    from hmac import compare_digest

    bearer: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()

    expected = settings.PLATFORM_API_KEY
    if expected and (
        (bearer is not None and compare_digest(bearer, expected))
        or (x_platform_api_key is not None and compare_digest(x_platform_api_key, expected))
    ):
        return True
    raise PermissionDeniedError("无效的 PLATFORM_API_KEY")
