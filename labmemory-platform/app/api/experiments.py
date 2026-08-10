"""实验管理（仅 PI）。

按用户需求 6：只有项目负责人可以操作实验管理。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_pi
from app.core.errors import ConflictError, NotFoundError
from app.db.models import Experiment, ExperimentMember, Project, User
from app.schemas import (
    ExperimentIn,
    ExperimentMemberIn,
    ExperimentMemberOut,
    ExperimentOut,
    ProjectOut,
)

router = APIRouter(prefix="/api", tags=["experiments"], dependencies=[Depends(require_pi)])


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectOut, db: Session = Depends(get_db), user: User = Depends(require_pi)) -> ProjectOut:
    if db.query(Project).filter(Project.project_id == payload.project_id).first():
        raise ConflictError(f"项目已存在：{payload.project_id}")
    proj = Project(
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        pi_user_id=user.id,
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return ProjectOut.model_validate(proj, from_attributes=True)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(require_pi)) -> list[ProjectOut]:
    qs = db.query(Project)
    if user.global_role != "admin":
        qs = qs.filter(Project.pi_user_id == user.id)
    return [ProjectOut.model_validate(p, from_attributes=True) for p in qs.all()]


@router.post("/experiments", response_model=ExperimentOut)
def create_experiment(payload: ExperimentIn, db: Session = Depends(get_db), user: User = Depends(require_pi)) -> ExperimentOut:
    proj = db.query(Project).filter(Project.project_id == payload.project_id).first()
    if proj is None:
        raise NotFoundError(f"项目不存在：{payload.project_id}")
    if db.query(Experiment).filter(Experiment.experiment_id == payload.experiment_id).first():
        raise ConflictError(f"实验已存在：{payload.experiment_id}")
    owner = db.query(User).filter(User.username == payload.owner_username).first()
    if owner is None:
        raise NotFoundError(f"用户不存在：{payload.owner_username}")
    exp = Experiment(
        experiment_id=payload.experiment_id,
        project_id=proj.id,
        name=payload.name,
        owner_user_id=owner.id,
        parameters_template=payload.parameters_template,
    )
    db.add(exp)
    db.flush()
    # 默认创建人为 PI 成员；owner 默认为 lead
    db.add(ExperimentMember(experiment_id=exp.id, user_id=user.id, role="pi"))
    if owner.id != user.id:
        db.add(ExperimentMember(experiment_id=exp.id, user_id=owner.id, role="lead"))
    db.commit()
    db.refresh(exp)
    return _experiment_out(db, exp)


@router.get("/experiments", response_model=list[ExperimentOut])
def list_experiments(db: Session = Depends(get_db), user: User = Depends(require_pi)) -> list[ExperimentOut]:
    qs = db.query(Experiment)
    if user.global_role != "admin":
        qs = qs.join(Project).filter(Project.pi_user_id == user.id)
    return [_experiment_out(db, e) for e in qs.all()]


@router.get("/experiments/{experiment_id}", response_model=ExperimentOut)
def get_experiment(experiment_id: str, db: Session = Depends(get_db)) -> ExperimentOut:
    exp = db.query(Experiment).filter(Experiment.experiment_id == experiment_id).first()
    if exp is None:
        raise NotFoundError(f"实验不存在：{experiment_id}")
    return _experiment_out(db, exp)


@router.post("/experiments/{experiment_id}/members", response_model=ExperimentOut)
def add_member(experiment_id: str, payload: ExperimentMemberIn, db: Session = Depends(get_db)) -> ExperimentOut:
    exp = db.query(Experiment).filter(Experiment.experiment_id == experiment_id).first()
    if exp is None:
        raise NotFoundError(f"实验不存在：{experiment_id}")
    u = db.query(User).filter(User.username == payload.username).first()
    if u is None:
        raise NotFoundError(f"用户不存在：{payload.username}")
    existing = db.query(ExperimentMember).filter(
        ExperimentMember.experiment_id == exp.id,
        ExperimentMember.user_id == u.id,
    ).first()
    if existing:
        existing.role = payload.role
    else:
        db.add(ExperimentMember(experiment_id=exp.id, user_id=u.id, role=payload.role))
    db.commit()
    db.refresh(exp)
    return _experiment_out(db, exp)


def _experiment_out(db: Session, exp: Experiment) -> ExperimentOut:
    members = (
        db.query(ExperimentMember, User)
        .join(User, User.id == ExperimentMember.user_id)
        .filter(ExperimentMember.experiment_id == exp.id)
        .all()
    )
    proj = db.get(Project, exp.project_id)
    return ExperimentOut(
        id=exp.id,
        experiment_id=exp.experiment_id,
        project_id=proj.project_id if proj else "",
        name=exp.name,
        status=exp.status,
        owner_user_id=exp.owner_user_id,
        parameters_template=exp.parameters_template,
        members=[
            ExperimentMemberOut(
                id=m.id,
                user_id=u.id,
                username=u.username,
                display_name=u.display_name,
                role=m.role,
            )
            for m, u in members
        ],
    )
