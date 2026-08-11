"""会议接入与会后复核。

/v1/* 接收 feishu-orchestrator 推送的 MeetingPackage / CandidatePackage；
/api/meetings/* 供平台前端操作复核。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, require_member, verify_platform_api_key, visible_experiment_ids, ensure_experiment_member
from app.core.errors import ConflictError, NotFoundError, StateTransitionError
from app.core.security import new_id
from app.db.models import (
    AuditEvent,
    Candidate,
    Claim,
    Experiment,
    Meeting,
    MeetingReview,
    Task,
    User,
)
from app.schemas import (
    CandidatePackageIn,
    MeetingChainItem,
    MeetingDetailOut,
    MeetingPackageIn,
    MeetingReviewOut,
    ReviewConfirmIn,
)

router = APIRouter(tags=["meetings"])

# === 飞书侧推送 ===

v1_router = APIRouter(prefix="/api/v1", tags=["integration"], dependencies=[Depends(verify_platform_api_key)])


@v1_router.post("/meetings")
def receive_meeting(payload: MeetingPackageIn, db: Session = Depends(get_db)):
    exp_id = (payload.metadata or {}).get("experiment_id")
    if not exp_id:
        raise NotFoundError("metadata.experiment_id 必填")
    exp = db.query(Experiment).filter(Experiment.experiment_id == exp_id).first()
    if exp is None:
        raise NotFoundError(f"实验不存在：{exp_id}（请先由 PI 创建实验）")

    existing = db.query(Meeting).filter(Meeting.meeting_id == payload.meeting_id).first()
    if existing:
        # 幂等：相同 meeting_id 返回已存在
        return {"meeting_id": existing.meeting_id, "id": existing.id, "created": False}

    transcript = (payload.content or {}).get("transcript") or []
    summary = (payload.content or {}).get("summary")
    meeting = Meeting(
        meeting_id=payload.meeting_id,
        experiment_id=exp.id,
        title=payload.title,
        source=payload.source,
        source_object_id=payload.source_object_id,
        source_url=payload.source_url,
        organizer=payload.organizer,
        participants=payload.participants,
        summary=summary,
        transcript=transcript,
        captured_at=payload.captured_at,
        raw_payload=payload.model_dump(mode="json"),
    )
    db.add(meeting)
    db.flush()
    # 自动创建 pending 复核记录
    review = MeetingReview(meeting_id=meeting.id, status="pending")
    db.add(review)
    db.commit()
    return {"meeting_id": meeting.meeting_id, "id": meeting.id, "created": True}


@v1_router.post("/candidates")
def receive_candidate(payload: CandidatePackageIn, db: Session = Depends(get_db)):
    # source_package_id 必须引用已接收的会议包
    meeting = db.query(Meeting).filter(
        Meeting.meeting_id == payload.source_package_id
    ).first()
    if meeting is None:
        # 也允许通过 metadata.meeting_id 关联（部分实现把 source_package_id 与 meeting_id 区分）
        raise NotFoundError(f"未找到关联会议：source_package_id={payload.source_package_id}")

    existing = db.query(Candidate).filter(
        Candidate.meeting_id == meeting.id,
        Candidate.source_package_id == payload.source_package_id,
    ).first()
    created = False
    if existing is None:
        cand = Candidate(
            meeting_id=meeting.id,
            source_package_id=payload.source_package_id,
            aily_skill_version=payload.aily_skill_version,
            candidates=payload.candidates,
            risks=payload.risks,
            action_items=payload.action_items,
            open_questions=payload.open_questions,
            compiled_at=payload.compiled_at,
            raw_payload=payload.model_dump(mode="json"),
        )
        db.add(cand)
        db.commit()
        db.refresh(cand)
        cand_id = cand.id
        created = True
    else:
        cand_id = existing.id

    # 契约响应：编排器 pipeline_orchestrator 读取 status 键
    review_count = (
        db.query(MeetingReview)
        .join(Meeting, Meeting.id == MeetingReview.meeting_id)
        .filter(Meeting.experiment_id == meeting.experiment_id, MeetingReview.status == "pending")
        .count()
    )
    results = [
        {"candidate_id": c.get("candidate_id"), "status": "pending_review"}
        for c in (payload.candidates or [])
    ]
    return {
        "id": cand_id,
        "created": created,
        "status": "submitted",
        "results": results,
        "review_count": review_count,
    }


# === 平台前端 ===

@router.get("/api/meetings", response_model=list[MeetingChainItem])
def list_meeting_reviews(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出待处理 / 已处理 复核会议。"""
    qs = (
        db.query(Meeting, MeetingReview)
        .join(MeetingReview, MeetingReview.meeting_id == Meeting.id)
        .order_by(Meeting.created_at.desc())
    )
    visible = visible_experiment_ids(db, user)
    if visible is not None:
        qs = qs.filter(Meeting.experiment_id.in_(visible))
    if status:
        qs = qs.filter(MeetingReview.status == status)
    out = []
    for m, r in qs.all():
        out.append(_chain_item(db, m, r))
    return out


@router.get("/api/meetings/{meeting_id}", response_model=MeetingDetailOut)
def get_meeting(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    m, r = _get_meeting_review(db, meeting_id)
    ensure_experiment_member(db, m.experiment_id, user)
    return _detail_out(db, m, r)


@router.get("/api/meetings/{meeting_id}/chain", response_model=MeetingChainItem)
def get_meeting_chain(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    m, r = _get_meeting_review(db, meeting_id)
    ensure_experiment_member(db, m.experiment_id, user)
    return _chain_item(db, m, r)


@router.post("/api/meetings/{meeting_id}/review", response_model=MeetingChainItem)
def confirm_review(
    meeting_id: str,
    payload: ReviewConfirmIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
):
    m, r = _get_meeting_review(db, meeting_id)
    if r.status != "pending":
        raise StateTransitionError(f"复核已处理：{r.decision}")
    # 校验是该实验成员
    exp = db.get(Experiment, m.experiment_id)
    from app.api.deps import ensure_experiment_member
    ensure_experiment_member(db, exp.id, user)

    r.status = "processed"
    r.decision = payload.decision
    r.reviewer_id = user.id
    r.reviewed_at = datetime.utcnow()
    r.modifications = payload.modifications
    r.notes = payload.notes

    if payload.decision == "ended":
        db.add(AuditEvent(
            actor_id=user.id, action="review.ended",
            target_type="meeting", target_id=m.meeting_id,
            after={"notes": payload.notes}, reason=payload.notes or "",
        ))
        db.commit()
        return _chain_item(db, m, r)

    # confirmed：六道闸门 + 冲突检测（PRD §10.1/10.5）决定发布状态
    from app.services.trust_rules import pick_candidate, run_six_gates, detect_conflicts
    cand = db.query(Candidate).filter(Candidate.meeting_id == m.id).first()
    chosen = pick_candidate(cand)
    gate = run_six_gates(chosen, payload.modifications, exp, user)
    new_params = (payload.modifications or {}).get("parameters") or (chosen or {}).get("parameters") or []
    new_scope = (payload.modifications or {}).get("scope") or (chosen or {}).get("scope")
    conflicts = detect_conflicts(db, exp.id, new_params, new_scope, user)
    blocked_by_conflict = any(c.get("severity") == "high" for c in conflicts)
    publish_status = "pending_supplement" if blocked_by_conflict else gate["publish_status"]

    claim = _build_claim(db, m, exp, cand, payload.modifications, publish_status=publish_status)
    db.add(claim)
    db.flush()

    task = None
    if publish_status == "current":
        task = Task(
            task_id=new_id("T"),
            meeting_id=m.id,
            experiment_id=exp.id,
            claim_id=claim.id,
            status="draft",
            planned_params=claim.parameter_version,
        )
        db.add(task)
        db.flush()

    db.add(AuditEvent(
        actor_id=user.id, action="review.confirmed",
        target_type="meeting", target_id=m.meeting_id,
        after={"claim_id": claim.claim_id, "task_id": task.task_id if task else None,
               "publish_status": publish_status, "gate_failed": gate["report"], "conflicts": conflicts},
        reason=(payload.reason or payload.notes or ""),
    ))
    db.commit()
    return _chain_item(db, m, r)


# === 内部辅助 ===

def _get_meeting_review(db: Session, meeting_id: str):
    m = db.query(Meeting).filter(Meeting.meeting_id == meeting_id).first()
    if m is None:
        raise NotFoundError(f"会议不存在：{meeting_id}")
    r = db.query(MeetingReview).filter(MeetingReview.meeting_id == m.id).first()
    if r is None:
        r = MeetingReview(meeting_id=m.id, status="pending")
        db.add(r)
        db.commit()
        db.refresh(r)
    return m, r


def _build_claim(
    db: Session,
    meeting: Meeting,
    experiment: Experiment,
    candidate: Candidate | None,
    modifications: dict | None,
    publish_status: str = "current",
) -> Claim:
    """从候选 + 复核修改生成主张。参数完全由候选/修改决定，不硬编码。"""
    candidates = (candidate.candidates if candidate else []) or []
    # 候选里挑出 parameter_change 或第一个作为主张对象
    chosen = next((c for c in candidates if c.get("type") == "parameter_change"), None)
    if chosen is None and candidates:
        chosen = candidates[0]

    if chosen:
        content = {
            "title": chosen.get("title"),
            "description": chosen.get("description"),
            "type": chosen.get("type"),
            "experiment_ref": chosen.get("experiment_ref"),
            "evidence": chosen.get("evidence", []),
            "confidence": chosen.get("confidence"),
        }
        params = chosen.get("parameters", []) or []
    else:
        content = {"title": meeting.title, "description": None, "type": None, "evidence": []}
        params = []

    # 复核修改：可覆盖 parameters / conditions / scope 等
    if modifications:
        if "parameters" in modifications:
            params = modifications["parameters"]
        if "conditions" in modifications:
            content["conditions"] = modifications["conditions"]
        if "scope" in modifications:
            content["scope"] = modifications["scope"]
        if "title" in modifications:
            content["title"] = modifications["title"]

    # 参数版本：按参数维度跟踪（PRD §10.3）——仅当发布为 current 时 supersede 旧主张并对比同名参数
    replaces_id = None
    old_param_versions: dict = {}
    if publish_status == "current":
        old_active = (
            db.query(Claim)
            .filter(Claim.experiment_id == experiment.id, Claim.status == "current")
            .order_by(Claim.created_at.desc())
            .first()
        )
        if old_active is not None:
            old_active.status = "superseded"
            replaces_id = old_active.id
            for p in ((old_active.parameter_version or {}).get("parameters") or []):
                old_param_versions[p.get("name")] = {"value": p.get("value"), "version": p.get("version", "v1")}

    # 每个参数独立版本：值相同继承（不升版），变化/新增升版
    versioned_params = []
    max_v = 1
    for p in params:
        name, new_val = p.get("name"), p.get("value")
        old = old_param_versions.get(name)
        if old is not None and str(old.get("value")) == str(new_val):
            v = old.get("version", "v1")  # 继承
        elif old is not None:
            try:
                v = f"v{int(str(old.get('version', 'v1')).lstrip('v')) + 1}"
            except (ValueError, TypeError):
                v = "v2"
        else:
            v = "v1"
        versioned_params.append({**p, "version": v})
        try:
            max_v = max(max_v, int(str(v).lstrip("v")))
        except (ValueError, TypeError):
            pass

    parameter_version = {
        "parameters": versioned_params,
        "version": f"v{max_v}",  # 顶层取最大，向后兼容
        "effective_at": datetime.utcnow().isoformat(),
        "scope": (modifications or {}).get("scope") or (content.get("scope") if modifications else None),
    }

    return Claim(
        claim_id=new_id("C"),
        meeting_id=meeting.id,
        experiment_id=experiment.id,
        content=content,
        parameter_version=parameter_version,
        status=publish_status,
        replaces_claim_id=replaces_id,
    )


def _chain_item(db: Session, m: Meeting, r: MeetingReview) -> MeetingChainItem:
    exp = db.get(Experiment, m.experiment_id)
    claim = db.query(Claim).filter(Claim.meeting_id == m.id).order_by(Claim.created_at.desc()).first()
    # 会议可能因一键修正有多个任务：取最新任务作为当前活跃代表（旧 blocked 任务保留历史）
    task = db.query(Task).filter(Task.meeting_id == m.id).order_by(Task.id.desc()).first()
    from app.api.tasks import _audit_out, _task_out
    from app.api.results import _result_out
    audit = None
    if task:
        from app.db.models import ActionAudit
        a = db.query(ActionAudit).filter(ActionAudit.task_id == task.id).first()
        if a:
            audit = _audit_out(a, task.task_id)
    results = []
    if task:
        from app.db.models import Result
        for res in db.query(Result).filter(Result.task_id == task.id).all():
            results.append(_result_out(res, task.task_id, task.planned_params))
    cand = db.query(Candidate).filter(Candidate.meeting_id == m.id).first()
    candidates_out = []
    if cand and cand.candidates:
        from app.schemas import CandidateOut
        for c in cand.candidates:
            candidates_out.append(CandidateOut(
                candidate_id=c.get("candidate_id", ""),
                type=c.get("type", ""),
                title=c.get("title", ""),
                description=c.get("description"),
                experiment_ref=c.get("experiment_ref"),
                parameters=c.get("parameters", []),
                confidence=c.get("confidence"),
                evidence=c.get("evidence", []),
                status=c.get("status"),
                needs_review=c.get("needs_review"),
            ))
    return MeetingChainItem(
        meeting_id=m.meeting_id,
        experiment_id=exp.experiment_id if exp else "",
        title=m.title,
        captured_at=m.captured_at,
        review=_review_out(m, r, exp.experiment_id if exp else ""),
        claim=_claim_out(claim, m.meeting_id, exp.experiment_id if exp else "") if claim else None,
        task=_task_out(task, m.meeting_id, exp.experiment_id if exp else "") if task else None,
        audit=audit,
        results=results,
        candidates=candidates_out,
        transcript=m.transcript or [],
        summary=m.summary,
    )


def _review_out(m: Meeting, r: MeetingReview, experiment_id: str) -> MeetingReviewOut:
    return MeetingReviewOut(
        id=r.id,
        meeting_id=m.meeting_id,
        experiment_id=experiment_id,
        status=r.status,
        decision=r.decision,
        reviewer_id=r.reviewer_id,
        reviewed_at=r.reviewed_at,
        modifications=r.modifications,
        notes=r.notes,
    )


def _detail_out(db: Session, m: Meeting, r: MeetingReview) -> MeetingDetailOut:
    chain = _chain_item(db, m, r)
    exp = db.get(Experiment, m.experiment_id)
    return MeetingDetailOut(
        meeting_id=chain.meeting_id,
        experiment_id=exp.experiment_id if exp else "",
        title=chain.title,
        source=m.source,
        source_url=m.source_url,
        organizer=m.organizer,
        participants=m.participants or [],
        summary=chain.summary,
        transcript=chain.transcript,
        captured_at=m.captured_at,
        candidates=chain.candidates,
        risks=(db.query(Candidate).filter(Candidate.meeting_id == m.id).first().risks or []) if db.query(Candidate).filter(Candidate.meeting_id == m.id).first() else [],
        action_items=(db.query(Candidate).filter(Candidate.meeting_id == m.id).first().action_items or []) if db.query(Candidate).filter(Candidate.meeting_id == m.id).first() else [],
        open_questions=(db.query(Candidate).filter(Candidate.meeting_id == m.id).first().open_questions or []) if db.query(Candidate).filter(Candidate.meeting_id == m.id).first() else [],
        review=chain.review,
        claim=chain.claim,
        task=chain.task,
        audit=chain.audit,
        results=chain.results,
    )


def _claim_out(claim: Claim, meeting_id: str, experiment_id: str):
    from app.schemas import ClaimOut
    return ClaimOut(
        id=claim.id,
        claim_id=claim.claim_id,
        meeting_id=meeting_id,
        experiment_id=experiment_id,
        content=claim.content,
        parameter_version=claim.parameter_version,
        status=claim.status,
        knowledge_status=claim.knowledge_status,
        replaces_claim_id=claim.replaces_claim_id,
    )


router.include_router(v1_router)
