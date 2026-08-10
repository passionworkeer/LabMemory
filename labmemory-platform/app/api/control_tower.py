"""研发控制塔：聚合首页指标。"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
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
    pending_reviews = (
        db.query(MeetingReview)
        .filter(MeetingReview.status == "pending")
        .count()
    )
    blocked_tasks = (
        db.query(Task)
        .filter(Task.status == "blocked")
        .count()
    )
    # 异常：frozen 结果 + blocked 任务
    anomalies = (
        db.query(Result).filter(Result.status == "frozen").count()
        + blocked_tasks
    )
    cutoff = datetime.utcnow() - timedelta(hours=24)
    published_24h = (
        db.query(Result)
        .filter(Result.status == "published", Result.published_at >= cutoff)
        .count()
    )
    active_experiments = (
        db.query(Experiment).filter(Experiment.status == "active").count()
    )

    # 需要处理：最近 5 条 pending 复核 + blocked 任务
    need_attention: list[dict] = []
    for m, r in (
        db.query(Meeting, MeetingReview)
        .join(MeetingReview, MeetingReview.meeting_id == Meeting.id)
        .filter(MeetingReview.status == "pending")
        .order_by(Meeting.created_at.desc())
        .limit(5)
        .all()
    ):
        exp = db.get(Experiment, m.experiment_id)
        need_attention.append({
            "type": "pending_review",
            "target_id": m.meeting_id,
            "experiment_id": exp.experiment_id if exp else "",
            "title": m.title,
            "status": "待复核",
            "severity": "normal",
        })
    for t in (
        db.query(Task)
        .filter(Task.status == "blocked")
        .order_by(Task.created_at.desc())
        .limit(5)
        .all()
    ):
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
