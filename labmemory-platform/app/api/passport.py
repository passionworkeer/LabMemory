"""实验护照。

按用户需求 9：
- 数据关系链：按会议 ID 组织（一个实验多个会议），可展开每次会议的流向。
- 统一时间线：按实验 ID 组织并展开，结果回流完成即会议任务结束。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.meetings import _chain_item
from app.api.deps import ensure_experiment_member
from app.core.errors import NotFoundError
from app.db.models import (
    AuditEvent,
    Claim,
    Experiment,
    ExperimentMember,
    Meeting,
    MeetingReview,
    Project,
    Result,
    Task,
    User,
)
from app.schemas import (
    ClaimOut,
    ExperimentMemberOut,
    ExperimentPassport,
    MeetingChainItem,
    PassportClaimSummary,
    PassportSummaryOut,
    TimelineEvent,
)

router = APIRouter(prefix="/api/experiments", tags=["passport"])
# 列表路由独立前缀，避免与 /api/experiments/{experiment_id} 冲突
list_router = APIRouter(prefix="/api", tags=["passport"])


@list_router.get("/passports", response_model=list[PassportSummaryOut])
def list_passports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """实验护照列表：admin 可见全部实验，其他角色（含 PI）仅可见自己参与（成员）的实验。"""
    qs = db.query(Experiment)
    if user.global_role != "admin":
        qs = (
            qs.join(ExperimentMember, ExperimentMember.experiment_id == Experiment.id)
            .filter(ExperimentMember.user_id == user.id)
        )
    exps = qs.order_by(Experiment.id.desc()).all()
    if not exps:
        return []
    exp_ids = [e.id for e in exps]

    meeting_counts = _count_by(db, Meeting, Meeting.experiment_id, exp_ids)
    pending_review_counts = dict(
        db.query(Meeting.experiment_id, func.count(MeetingReview.id))
        .join(MeetingReview, MeetingReview.meeting_id == Meeting.id)
        .filter(Meeting.experiment_id.in_(exp_ids), MeetingReview.status == "pending")
        .group_by(Meeting.experiment_id)
        .all()
    )
    task_counts = _count_by(db, Task, Task.experiment_id, exp_ids)
    blocked_task_counts = dict(
        db.query(Task.experiment_id, func.count(Task.id))
        .filter(Task.experiment_id.in_(exp_ids), Task.status == "blocked")
        .group_by(Task.experiment_id)
        .all()
    )
    published_counts = dict(
        db.query(Task.experiment_id, func.count(Result.id))
        .join(Result, Result.task_id == Task.id)
        .filter(Task.experiment_id.in_(exp_ids), Result.status == "published")
        .group_by(Task.experiment_id)
        .all()
    )

    # 最近活动：会议/任务/结果/主张 时间戳取最大值（结果表无 experiment_id，经任务关联）
    last_activity: dict[int, datetime] = {}
    for model, ts_col in ((Meeting, Meeting.captured_at), (Task, Task.created_at), (Claim, Claim.created_at)):
        rows = (
            db.query(model.experiment_id, func.max(ts_col))
            .filter(model.experiment_id.in_(exp_ids))
            .group_by(model.experiment_id)
            .all()
        )
        for eid, ts in rows:
            if ts and (eid not in last_activity or ts > last_activity[eid]):
                last_activity[eid] = ts
    for eid, ts in (
        db.query(Task.experiment_id, func.max(Result.created_at))
        .join(Result, Result.task_id == Task.id)
        .filter(Task.experiment_id.in_(exp_ids))
        .group_by(Task.experiment_id)
        .all()
    ):
        if ts and (eid not in last_activity or ts > last_activity[eid]):
            last_activity[eid] = ts

    # 当前有效主张（status=current，最新优先）
    claims = (
        db.query(Claim)
        .filter(Claim.experiment_id.in_(exp_ids), Claim.status == "current")
        .order_by(Claim.id.desc())
        .all()
    )
    current_by_exp: dict[int, Claim] = {}
    for c in claims:
        current_by_exp.setdefault(c.experiment_id, c)

    members_by_exp: dict[int, list[ExperimentMemberOut]] = defaultdict(list)
    for m, u in (
        db.query(ExperimentMember, User)
        .join(User, User.id == ExperimentMember.user_id)
        .filter(ExperimentMember.experiment_id.in_(exp_ids))
        .order_by(ExperimentMember.id.asc())
        .all()
    ):
        members_by_exp[m.experiment_id].append(
            ExperimentMemberOut(
                id=m.id, user_id=u.id, username=u.username, display_name=u.display_name, role=m.role
            )
        )

    owner_names = dict(
        db.query(User.id, User.display_name).filter(User.id.in_([e.owner_user_id for e in exps])).all()
    )
    project_ids = dict(
        db.query(Project.id, Project.project_id).filter(Project.id.in_([e.project_id for e in exps])).all()
    )

    return [
        PassportSummaryOut(
            experiment_id=e.experiment_id,
            project_id=project_ids.get(e.project_id, ""),
            name=e.name,
            status=e.status,
            owner_display_name=owner_names.get(e.owner_user_id, ""),
            members=members_by_exp.get(e.id, []),
            meeting_count=meeting_counts.get(e.id, 0),
            pending_review_count=pending_review_counts.get(e.id, 0),
            current_claim=_claim_summary(current_by_exp.get(e.id)),
            task_count=task_counts.get(e.id, 0),
            blocked_task_count=blocked_task_counts.get(e.id, 0),
            published_result_count=published_counts.get(e.id, 0),
            last_activity_at=last_activity.get(e.id),
        )
        for e in exps
    ]


def _count_by(db: Session, model, exp_col, exp_ids) -> dict[int, int]:
    return dict(
        db.query(exp_col, func.count(model.id))
        .filter(exp_col.in_(exp_ids))
        .group_by(exp_col)
        .all()
    )


def _claim_summary(c: Claim | None) -> PassportClaimSummary | None:
    if c is None:
        return None
    return PassportClaimSummary(
        claim_id=c.claim_id,
        status=c.status,
        knowledge_status=c.knowledge_status,
        parameter_version=c.parameter_version,
    )


@router.get("/{experiment_id}/passport", response_model=ExperimentPassport)
def get_passport(experiment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    exp = db.query(Experiment).filter(Experiment.experiment_id == experiment_id).first()
    if exp is None:
        raise NotFoundError(f"实验不存在：{experiment_id}")
    # admin 可查看所有实验；其他角色（含 PI）需为成员
    if user.global_role != "admin":
        ensure_experiment_member(db, exp.id, user)
    proj = db.get(Project, exp.project_id)

    # 数据关系链：按会议 ID 组织
    rows = (
        db.query(Meeting, MeetingReview)
        .join(MeetingReview, MeetingReview.meeting_id == Meeting.id)
        .filter(Meeting.experiment_id == exp.id)
        .order_by(Meeting.captured_at.asc())
        .all()
    )
    meetings = [_chain_item(db, m, r) for m, r in rows]

    # 当前有效主张（status=current 即未被替代；knowledge_status 反映验证结果）
    current_claim = db.query(Claim).filter(
        Claim.experiment_id == exp.id,
        Claim.status == "current",
    ).order_by(Claim.created_at.desc()).first()
    current_claim_out = None
    if current_claim:
        cm = db.get(Meeting, current_claim.meeting_id)
        current_claim_out = ClaimOut(
            id=current_claim.id,
            claim_id=current_claim.claim_id,
            meeting_id=cm.meeting_id if cm else "",
            experiment_id=experiment_id,
            content=current_claim.content,
            parameter_version=current_claim.parameter_version,
            status=current_claim.status,
            knowledge_status=current_claim.knowledge_status,
            replaces_claim_id=current_claim.replaces_claim_id,
        )

    # 统一时间线：按实验 ID 组织，按时间排序
    target_ids: set[str] = set()
    for m, _ in rows:
        target_ids.add(m.meeting_id)
    claims = db.query(Claim).filter(Claim.experiment_id == exp.id).all()
    for c in claims:
        target_ids.add(c.claim_id)
    from app.db.models import ActionAudit
    tasks = db.query(Task).filter(Task.experiment_id == exp.id).all()
    for t in tasks:
        target_ids.add(t.task_id)
    for t in tasks:
        results = db.query(Result).filter(Result.task_id == t.id).all()
        for r in results:
            target_ids.add(r.result_id)
        audits = db.query(ActionAudit).filter(ActionAudit.task_id == t.id).all()
        for a in audits:
            target_ids.add(str(a.id))

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.target_id.in_(target_ids))
        .order_by(AuditEvent.created_at.asc())
        .all()
    )
    timeline = [
        TimelineEvent(
            timestamp=e.created_at,
            event_type=e.action,
            actor_id=e.actor_id,
            target_type=e.target_type,
            target_id=e.target_id,
            summary=f"{e.action} -> {e.target_type}:{e.target_id}",
            details={"before": e.before, "after": e.after, "reason": e.reason},
        )
        for e in events
    ]

    return ExperimentPassport(
        experiment_id=experiment_id,
        project_id=proj.project_id if proj else "",
        name=exp.name,
        status=exp.status,
        current_claim=current_claim_out,
        meetings=meetings,
        timeline=timeline,
    )
