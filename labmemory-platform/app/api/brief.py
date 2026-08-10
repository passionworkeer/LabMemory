"""会前研讨包：实验当前上下文。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import ensure_experiment_member, get_current_user, get_db
from app.api.meetings import _claim_out
from app.api.results import _result_out
from app.core.errors import NotFoundError
from app.db.models import Claim, Experiment, Meeting, Result, Task, User
from app.schemas import ExperimentBrief

router = APIRouter(prefix="/api/experiments", tags=["brief"])


@router.get("/{experiment_id}/brief", response_model=ExperimentBrief)
def get_brief(experiment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    exp = db.query(Experiment).filter(Experiment.experiment_id == experiment_id).first()
    if exp is None:
        raise NotFoundError(f"实验不存在：{experiment_id}")
    if user.global_role not in ("admin", "pi"):
        ensure_experiment_member(db, exp.id, user)

    # 当前主张
    current_claim = (
        db.query(Claim)
        .filter(Claim.experiment_id == exp.id, Claim.status == "current")
        .order_by(Claim.created_at.desc())
        .first()
    )
    current_claim_out = None
    if current_claim:
        cm = db.get(Meeting, current_claim.meeting_id)
        current_claim_out = _claim_out(current_claim, cm.meeting_id if cm else "", experiment_id)

    # 上一轮结果（最近一条 published 结果）
    last_result = None
    last_task = None
    last_res = (
        db.query(Result)
        .join(Task, Task.id == Result.task_id)
        .filter(Task.experiment_id == exp.id, Result.status == "published")
        .order_by(Result.published_at.desc())
        .first()
    )
    if last_res:
        last_task = db.get(Task, last_res.task_id)
        last_result = _result_out(last_res, last_task.task_id if last_task else "", last_task.planned_params if last_task else None)

    # 失败边界：从已发布结果的 failure_boundary 字段聚合
    failure_boundaries: list[dict] = []
    for r in (
        db.query(Result)
        .join(Task, Task.id == Result.task_id)
        .filter(Task.experiment_id == exp.id, Result.failure_boundary.isnot(None))
        .all()
    ):
        if r.failure_boundary:
            failure_boundaries.append(r.failure_boundary)

    # 当前目标：取最近一次会议的 summary
    last_meeting = (
        db.query(Meeting)
        .filter(Meeting.experiment_id == exp.id)
        .order_by(Meeting.captured_at.desc())
        .first()
    )

    return ExperimentBrief(
        experiment_id=experiment_id,
        project_id="",  # 由前端从 passport 拼接
        name=exp.name,
        status=exp.status,
        current_goal=last_meeting.summary if last_meeting else None,
        current_claim=current_claim_out,
        last_result=last_result,
        failure_boundaries=failure_boundaries,
        resources={"note": "简化版未接入物料/设备系统"},
        pending_questions=[],
    )
