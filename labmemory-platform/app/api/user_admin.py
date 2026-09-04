"""管理员用户管理：UUAP 自动注册用户的角色与可见范围控制。

需求背景：新用户通过飞书 UUAP 免登自动注册（默认 viewer 最低权限，无成员关系时
不可见任何实验）。管理员在本模块：

- 查看全部用户（含来源 seed / feishu_auto / manual）
- 调整用户全局角色（viewer / executor / lead / pi / admin）
- 通过增删「实验成员」精确控制每个用户能看到的实验范围（实验级角色 viewer/executor/lead/pi）

安全约束：
- 仅全局 admin 可访问
- 禁止管理员把「自己」降级为非 admin（避免锁死）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.db.models import Experiment, ExperimentMember, User
from app.schemas import ExperimentMemberOut, UserAdminOut, UserMemberAddIn, UserRolePatchIn

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _user_admin_out(db: Session, user: User) -> UserAdminOut:
    members = (
        db.query(ExperimentMember, Experiment)
        .join(Experiment, Experiment.id == ExperimentMember.experiment_id)
        .filter(ExperimentMember.user_id == user.id)
        .all()
    )
    return UserAdminOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        global_role=user.global_role,
        source=user.source,
        feishu_user_id=user.feishu_user_id,
        created_at=user.created_at,
        experiment_count=len(members),
        members=[
            ExperimentMemberOut(
                id=m.id,
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                role=m.role,
                experiment_id=exp.experiment_id,
            )
            for m, exp in members
        ],
    )


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"用户不存在：{user_id}")
    return user


def _get_experiment_by_str_or_404(db: Session, experiment_id: str) -> Experiment:
    exp = db.query(Experiment).filter(Experiment.experiment_id == experiment_id).first()
    if exp is None:
        raise NotFoundError(f"实验不存在：{experiment_id}")
    return exp


@router.get("/users", response_model=list[UserAdminOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[UserAdminOut]:
    """用户列表（管理员）：含全局角色、来源与可见实验成员关系。"""
    users = db.query(User).order_by(User.id.asc()).all()
    return [_user_admin_out(db, u) for u in users]


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def patch_user_role(
    user_id: int,
    payload: UserRolePatchIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserAdminOut:
    """调整用户全局角色（viewer / executor / lead / pi / admin）。"""
    user = _get_user_or_404(db, user_id)
    if user.id == admin.id and payload.global_role != "admin":
        raise PermissionDeniedError("不能移除自己的管理员角色（避免锁死）")
    user.global_role = payload.global_role
    db.commit()
    db.refresh(user)
    return _user_admin_out(db, user)


@router.post("/users/{user_id}/members", response_model=UserAdminOut)
def add_user_member(
    user_id: int,
    payload: UserMemberAddIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserAdminOut:
    """给用户添加实验成员关系（决定其能看到的实验范围与实验内角色）。"""
    user = _get_user_or_404(db, user_id)
    exp = _get_experiment_by_str_or_404(db, payload.experiment_id)
    existing = (
        db.query(ExperimentMember)
        .filter(
            ExperimentMember.experiment_id == exp.id,
            ExperimentMember.user_id == user.id,
        )
        .first()
    )
    if existing:
        existing.role = payload.role
    else:
        db.add(ExperimentMember(experiment_id=exp.id, user_id=user.id, role=payload.role))
    db.commit()
    db.refresh(user)
    return _user_admin_out(db, user)


@router.delete("/users/{user_id}/members/{experiment_id}", response_model=UserAdminOut)
def remove_user_member(
    user_id: int,
    experiment_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserAdminOut:
    """移除用户在某实验的成员关系（收回对该实验的可见范围）。"""
    user = _get_user_or_404(db, user_id)
    exp = _get_experiment_by_str_or_404(db, experiment_id)
    m = (
        db.query(ExperimentMember)
        .filter(
            ExperimentMember.experiment_id == exp.id,
            ExperimentMember.user_id == user.id,
        )
        .first()
    )
    if m is None:
        raise ConflictError(f"用户 {user.username} 不是实验 {experiment_id} 的成员")
    db.delete(m)
    db.commit()
    db.refresh(user)
    return _user_admin_out(db, user)
