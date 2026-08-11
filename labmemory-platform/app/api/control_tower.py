"""研发控制塔：聚合首页指标。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, visible_experiment_ids
from app.db.models import (
    ActionAudit,
    AuditEvent,
    Claim,
    Experiment,
    Meeting,
    MeetingReview,
    Result,
    Task,
    User,
)
from app.schemas import ControlTowerOut

router = APIRouter(prefix="/api/control-tower", tags=["control-tower"])


@router.get("", response_model=ControlTowerOut)
def get_control_tower(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    visible = visible_experiment_ids(db, user)  # None=全局(admin)；否则限本人可见实验

    def _exp_filter(model_expr):
        return model_expr.in_(visible) if visible is not None else None

    pending_q = (
        db.query(MeetingReview)
        .join(Meeting, Meeting.id == MeetingReview.meeting_id)
    )
    blocked_q = db.query(Task).filter(Task.status == "blocked")
    frozen_q = db.query(Result).join(Task, Task.id == Result.task_id).filter(Result.status == "frozen")
    if visible is not None:
        pending_q = pending_q.filter(Meeting.experiment_id.in_(visible))
        blocked_q = blocked_q.filter(Task.experiment_id.in_(visible))
        frozen_q = frozen_q.filter(Task.experiment_id.in_(visible))

    pending_reviews = pending_q.filter(MeetingReview.status == "pending").count()
    blocked_tasks = blocked_q.count()
    anomalies = frozen_q.count() + blocked_tasks
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    published_q = (
        db.query(Result)
        .join(Task, Task.id == Result.task_id)
        .filter(Result.status == "published", Result.published_at >= cutoff)
    )
    if visible is not None:
        published_q = published_q.filter(Task.experiment_id.in_(visible))
    published_24h = published_q.count()
    active_exp_q = db.query(Experiment).filter(Experiment.status == "active")
    if visible is not None:
        active_exp_q = active_exp_q.filter(Experiment.id.in_(visible))
    active_experiments = active_exp_q.count()

    # 需要处理：最近 5 条 pending 复核 + blocked 任务（按可见域）
    need_attention: list[dict] = []
    pending_rows = (
        db.query(Meeting, MeetingReview)
        .join(MeetingReview, MeetingReview.meeting_id == Meeting.id)
        .filter(MeetingReview.status == "pending")
        .order_by(Meeting.created_at.desc())
        .limit(5)
        .all()
    )
    if visible is not None:
        pending_rows = [row for row in pending_rows if row[0].experiment_id in visible]
    for m, r in pending_rows:
        exp = db.get(Experiment, m.experiment_id)
        need_attention.append({
            "type": "pending_review",
            "target_id": m.meeting_id,
            "experiment_id": exp.experiment_id if exp else "",
            "title": m.title,
            "status": "待复核",
            "severity": "normal",
        })
    blocked_rows = (
        db.query(Task)
        .filter(Task.status == "blocked")
        .order_by(Task.created_at.desc())
        .limit(5)
        .all()
    )
    if visible is not None:
        blocked_rows = [row for row in blocked_rows if row.experiment_id in visible]
    for t in blocked_rows:
        mt = db.get(Meeting, t.meeting_id)
        exp = db.get(Experiment, t.experiment_id)
        need_attention.append({
            "type": "blocked_task",
            "target_id": t.task_id,
            "experiment_id": exp.experiment_id if exp else "",
            "title": mt.title if mt else t.task_id,
            "status": "已阻断",
            "severity": "high",
        })

    return ControlTowerOut(
        pending_reviews=pending_reviews,
        blocked_tasks=blocked_tasks,
        anomalies=anomalies,
        published_24h=published_24h,
        active_experiments=active_experiments,
        need_attention=need_attention,
    )
