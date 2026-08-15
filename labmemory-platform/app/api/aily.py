"""Aily 集成契约（/v1/* 入站接口）。

与现有 /api/v1/* 并存：这是 Aily 侧的细粒度 ID 契约，鉴权同为 Bearer {PLATFORM_API_KEY}。
请求体统一用 dict（草版字段），复用现有领域逻辑（六道闸门 / 主张版本 / 审计 / 结果 / 护照）。
业务内核（ID 映射 / 候选构建 / 决策确认）从本文件抽到 `app.services.aily_helpers`，
以便 MCP Server 工具与 HTTP 端点共享同一份逻辑。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_platform_api_key
from app.core.errors import NotFoundError, StateTransitionError
from app.core.security import new_id
from app.db.models import (
    ActionAudit,
    AuditEvent,
    Candidate,
    Claim,
    Experiment,
    IntegrationRef,
    Meeting,
    MeetingReview,
    Result,
    Task,
    User,
)
from app.services.aily_helpers import (
    build_candidates,
    candidate_ids,
    confirm_decision,
    experiment,
    jump_url,
    meeting_from_ref,
    parse_dt,
    platform_id_from_ref,
    ref_get,
    ref_put,
    resolve_actor,
)
from app.services.aily_webhook import emit_event

aily_router = APIRouter(prefix="/v1", tags=["aily-integration"], dependencies=[Depends(verify_platform_api_key)])

DEFAULT_EXPERIMENT_ID = "EXP-DEMO-001"

@aily_router.post("/transcripts")
def receive_transcript(payload: dict, db: Session = Depends(get_db)):
    """收妙记/逐字稿：meeting_id, note_id, speakers[], segments[{start,end,speaker,text}]。"""
    meeting_id = payload.get("meeting_id")
    if not meeting_id:
        raise NotFoundError("meeting_id 必填")
    exp_id = payload.get("experiment_id") or (payload.get("metadata") or {}).get("experiment_id") or DEFAULT_EXPERIMENT_ID
    exp = experiment(db, exp_id)

    existing = db.query(Meeting).filter(Meeting.meeting_id == meeting_id).first()
    if existing is not None:
        ref_put(db, "transcript", meeting_id, "meeting", meeting_id)
        db.commit()
        return {"transcript_id": meeting_id, "created": False}

    segments = payload.get("segments") or []
    transcript = [
        {
            "speaker": s.get("speaker"),
            "start_offset_sec": s.get("start"),
            "end_offset_sec": s.get("end"),
            "text": s.get("text"),
        }
        for s in segments if isinstance(s, dict)
    ]
    meeting = Meeting(
        meeting_id=meeting_id,
        experiment_id=exp.id,
        title=payload.get("title") or payload.get("note_id") or meeting_id,
        source="aily",
        source_object_id=payload.get("note_id"),
        participants=payload.get("speakers") or [],
        summary=payload.get("summary"),
        transcript=transcript,
        captured_at=datetime.now(timezone.utc),
        raw_payload=payload,
    )
    db.add(meeting)
    db.flush()
    db.add(MeetingReview(meeting_id=meeting.id, status="pending"))
    ref_put(db, "transcript", meeting_id, "meeting", meeting_id)
    db.commit()
    return {"transcript_id": meeting_id, "meeting_id": meeting_id, "created": True}


@aily_router.post("/extractions")
def receive_extraction(payload: dict, db: Session = Depends(get_db)):
    """Aily 抽取回写：transcript_id, params[], disputes[], risks[], task_candidates[]。"""
    transcript_id = payload.get("transcript_id")
    meeting = meeting_from_ref(db, "transcript", transcript_id or "")
    if meeting is None:
        raise NotFoundError(f"逐字稿不存在：{transcript_id}")
    exp = db.get(Experiment, meeting.experiment_id)

    extraction_id = payload.get("extraction_id") or new_id("EXT")
    existing = db.query(Candidate).filter(Candidate.source_package_id == extraction_id).first()
    if existing is None:
        cand = Candidate(
            meeting_id=meeting.id,
            source_package_id=extraction_id,
            aily_skill_version=payload.get("aily_skill_version") or "aily-labmemory-v1.0",
            candidates=build_candidates(db, exp, payload),
            risks=payload.get("risks") or [],
            action_items=payload.get("task_candidates") or [],
            open_questions=payload.get("disputes") or [],
            compiled_at=datetime.now(timezone.utc),
            raw_payload=payload,
        )
        db.add(cand)
        db.flush()
        ref_put(db, "extraction", extraction_id, "meeting", meeting.meeting_id)
        db.commit()
        created = True
    else:
        created = False

    return {
        "extraction_id": extraction_id,
        "created": created,
        "candidate_ids": candidate_ids(db, meeting),
    }


@aily_router.post("/decision-inbox")
def create_decision(payload: dict, db: Session = Depends(get_db)):
    """创建待人工复核项：extraction_id, jump_url。返回 decision_id。"""
    extraction_id = payload.get("extraction_id")
    meeting = meeting_from_ref(db, "extraction", extraction_id or "")
    if meeting is None:
        raise NotFoundError(f"抽取不存在：{extraction_id}")

    review = db.query(MeetingReview).filter(MeetingReview.meeting_id == meeting.id).first()
    if review is None:
        review = MeetingReview(meeting_id=meeting.id, status="pending")
        db.add(review)
        db.flush()

    decision_id = payload.get("decision_id") or new_id("DEC")
    ref_put(db, "decision", decision_id, "review", meeting.meeting_id)
    db.commit()

    emit_event("decision.pending", {
        "decision_id": decision_id,
        "transcript_id": platform_id_from_ref(db, "transcript", meeting.meeting_id),
        "extraction_id": extraction_id,
        "assignee": payload.get("assignee"),
        "jump_url": payload.get("jump_url") or jump_url(f"/review/{meeting.meeting_id}"),
    }, idempotency_key=f"decision.pending:{decision_id}")

    return {"decision_id": decision_id, "meeting_id": meeting.meeting_id, "jump_url": payload.get("jump_url") or jump_url(f"/review/{meeting.meeting_id}")}


@aily_router.post("/decision-inbox/{decision_id}/verdict")
def decision_verdict(decision_id: str, payload: dict, db: Session = Depends(get_db)):
    """人在平台点通过/驳回：verdict(pass/reject), reviewer, comment, verdict_at。"""
    meeting = meeting_from_ref(db, "decision", decision_id)
    if meeting is None:
        raise NotFoundError(f"决策项不存在：{decision_id}")
    review = db.query(MeetingReview).filter(MeetingReview.meeting_id == meeting.id).first()
    actor = resolve_actor(db, payload.get("reviewer"))
    verdict = payload.get("verdict")

    if verdict == "reject":
        if review and review.status == "pending":
            review.status = "processed"
            review.decision = "ended"
            review.reviewer_id = actor.id if actor else None
            review.reviewed_at = datetime.now(timezone.utc)
            review.notes = payload.get("comment")
        db.commit()
        return {"ack": True, "decision_id": decision_id, "verdict": "reject"}

    # pass：复用复核确认 + 六道闸门 + 主张/任务生成
    if review is None:
        review = MeetingReview(meeting_id=meeting.id, status="pending")
        db.add(review)
        db.flush()
    claim, task, publish_status, gate, conflicts = confirm_decision(db, meeting, review, actor, payload.get("comment"))
    db.commit()

    return {
        "ack": True,
        "decision_id": decision_id,
        "verdict": "pass",
        "version_id": claim.claim_id if claim else None,
        "task_id": task.task_id if task else None,
        "publish_status": publish_status,
        "gate_report": gate["report"] + [c["message"] for c in conflicts],
    }


@aily_router.post("/parameter-versions")
def issue_parameter_version(payload: dict, db: Session = Depends(get_db)):
    """签发正式参数版本：decision_id, params[], effective_from, evidence_refs[]。返回 version_id。"""
    decision_id = payload.get("decision_id")
    meeting = meeting_from_ref(db, "decision", decision_id or "")
    if meeting is None:
        raise NotFoundError(f"决策项不存在：{decision_id}")

    existing = db.query(Claim).filter(Claim.meeting_id == meeting.id).order_by(Claim.id.desc()).first()
    if existing is not None:
        ref_put(db, "version", existing.claim_id, "claim", existing.claim_id)
        db.commit()
        return {"version_id": existing.claim_id, "created": False, "params": existing.parameter_version}

    review = db.query(MeetingReview).filter(MeetingReview.meeting_id == meeting.id).first()
    if review is None:
        review = MeetingReview(meeting_id=meeting.id, status="pending")
        db.add(review)
        db.flush()
    actor = resolve_actor(db, None)
    claim, _task, publish_status, _gate, _conflicts = confirm_decision(db, meeting, review, actor, None)
    db.commit()
    return {"version_id": claim.claim_id, "created": True, "publish_status": publish_status}


@aily_router.post("/preflight")
def preflight(payload: dict, db: Session = Depends(get_db)):
    """执行前自检：version_id, executor, planned_at → verdict(ok/block), reasons[], boundary_check{}。"""
    from app.api.tasks import _run_checks

    version_id = payload.get("version_id")
    claim = db.query(Claim).filter(Claim.claim_id == version_id).first()
    if claim is None:
        raise NotFoundError(f"参数版本不存在：{version_id}")
    task = db.query(Task).filter(Task.claim_id == claim.id).order_by(Task.id.desc()).first()
    if task is None:
        raise NotFoundError(f"版本 {version_id} 未生成任务")

    exp = db.get(Experiment, task.experiment_id)
    checks = _run_checks(task, exp, db)
    verdict = "ok" if checks["overall"] == "passed" else "block"
    boundary = checks["items"].get("failure_boundary", {})

    if verdict == "block":
        emit_event("preflight.blocked", {
            "preflight_id": new_id("PRE"),
            "version_id": version_id,
            "reasons": checks["reasons"] + checks["confirmations"],
            "executor": payload.get("executor"),
            "jump_url": jump_url(f"/audit/{task.task_id}"),
        }, idempotency_key=f"preflight.blocked:{task.task_id}")

    return {"verdict": verdict, "reasons": checks["reasons"] + checks["confirmations"], "boundary_check": boundary, "task_id": task.task_id}


@aily_router.post("/executions")
def execution(payload: dict, db: Session = Depends(get_db)):
    """实际执行结果回写：version_id, actual_params{}, results{}, executor, executed_at → execution_id。"""
    version_id = payload.get("version_id")
    claim = db.query(Claim).filter(Claim.claim_id == version_id).first()
    if claim is None:
        raise NotFoundError(f"参数版本不存在：{version_id}")
    task = db.query(Task).filter(Task.claim_id == claim.id).order_by(Task.id.desc()).first()
    if task is None:
        raise NotFoundError(f"版本 {version_id} 未生成任务")
    if task.status not in ("running", "audited", "draft", "needs_confirmation", "blocked", "completed"):
        raise StateTransitionError(f"任务状态 {task.status} 不可回写执行")

    existing = db.query(Result).filter(Result.task_id == task.id).first()
    if existing is not None:
        return {"execution_id": existing.result_id, "created": False}

    planned = task.planned_params or {}
    planned_keys = {(p.get("name") if isinstance(p, dict) else None) for p in planned.get("parameters", [])} - {None}
    actual = payload.get("actual_params") or {}
    actual_keys = set(actual.keys())
    frozen = bool(planned_keys and not actual_keys.issubset(planned_keys))
    status = "frozen" if frozen else "submitted"

    actor = resolve_actor(db, payload.get("executor"))
    if actor is None:
        raise StateTransitionError("无法识别执行人，无法回写执行结果")
    res = Result(
        result_id=new_id("R"),
        task_id=task.id,
        submitter_id=actor.id,
        actual_params=actual,
        metrics=payload.get("results") or {},
        status=status,
    )
    db.add(res)
    if task.status != "completed":
        task.status = "completed"
    db.flush()
    ref_put(db, "execution", res.result_id, "result", res.result_id)
    db.commit()

    if frozen:
        emit_event("execution.deviated", {
            "execution_id": res.result_id,
            "version_id": version_id,
            "diff": {"planned_keys": sorted(planned_keys), "actual_keys": sorted(actual_keys)},
        }, idempotency_key=f"execution.deviated:{res.result_id}")

    return {"execution_id": res.result_id, "status": status, "created": True}


@aily_router.patch("/passports/{passport_id}")
def update_passport(passport_id: str, payload: dict, db: Session = Depends(get_db)):
    """更新实验护照/主张状态/失败边界：status, failure_boundary{}, claim_state。"""
    exp = experiment(db, passport_id)
    # claim_state → 当前主张 knowledge_status；failure_boundary → 挂到最新已发布结果（或主张）
    claim_state = payload.get("claim_state")
    if claim_state:
        current = db.query(Claim).filter(Claim.experiment_id == exp.id, Claim.status == "current").order_by(Claim.id.desc()).first()
        if current is not None:
            current.knowledge_status = claim_state

    fb = payload.get("failure_boundary")
    if fb:
        latest = db.query(Result).join(Task, Task.id == Result.task_id).filter(Task.experiment_id == exp.id).order_by(Result.id.desc()).first()
        if latest is not None:
            latest.failure_boundary = fb

    db.commit()
    return {"passport_id": passport_id, "experiment_id": exp.experiment_id, "updated": True}


@aily_router.post("/knowledge")
def knowledge(payload: dict, db: Session = Depends(get_db)):
    """知识发布：passport_id, title, summary, doc_refs[] → knowledge_id。

    M4 修复：幂等——同一实验最新已发布结果再次调用时直接返回原 knowledge_id，
    不重复写入 publisher_id/published_at/claim、不重复触发 webhook。
    判定：最新 result（submitted OR published）状态为 published 即视为已发。
    """
    exp = experiment(db, payload.get("passport_id") or "")
    latest = (
        db.query(Result)
        .join(Task, Task.id == Result.task_id)
        .filter(Task.experiment_id == exp.id, Result.status.in_(["submitted", "published"]))
        .order_by(Result.id.desc())
        .first()
    )
    if latest is None:
        raise NotFoundError("无可发布结果（需先回写 execution）")

    # M4 幂等短路：已 published 直接返回，不副作用
    if latest.status == "published":
        return {
            "knowledge_id": latest.result_id,
            "title": payload.get("title"),
            "status": "published",
            "idempotent": True,
        }

    latest.status = "published"
    latest.publisher_id = resolve_actor(db, None).id if resolve_actor(db, None) else None
    latest.published_at = datetime.now(timezone.utc)
    latest.knowledge_status = payload.get("claim_state") or "supported"
    latest.notes = payload.get("summary")
    task = db.get(Task, latest.task_id)
    if task and task.claim_id:
        claim = db.get(Claim, task.claim_id)
        if claim and claim.status == "current":
            claim.knowledge_status = latest.knowledge_status
    ref_put(db, "knowledge", latest.result_id, "result", latest.result_id)
    db.commit()

    emit_event("knowledge.ready", {
        "knowledge_id": latest.result_id,
        "passport_id": exp.experiment_id,
        "jump_url": jump_url(f"/result/{task.task_id if task else ''}"),
    }, idempotency_key=f"knowledge.ready:{latest.result_id}")

    return {"knowledge_id": latest.result_id, "title": payload.get("title"), "status": "published"}


@aily_router.post("/reverify-tasks")
def reverify_task(payload: dict, db: Session = Depends(get_db)):
    """创建复验任务：passport_id, assignee, due_at, criteria[] → reverify_id。"""
    exp = experiment(db, payload.get("passport_id") or "")
    current = db.query(Claim).filter(Claim.experiment_id == exp.id, Claim.status == "current").order_by(Claim.id.desc()).first()
    if current is None:
        raise NotFoundError("实验无当前主张，无法创建复验任务")
    meeting = db.get(Meeting, current.meeting_id)
    actor = resolve_actor(db, payload.get("assignee"))

    task = Task(
        task_id=new_id("RV"),
        meeting_id=current.meeting_id,
        experiment_id=exp.id,
        claim_id=current.id,
        status="draft",
        planned_params=current.parameter_version,
        assignee_id=actor.id if actor else None,
        due_date=parse_dt(payload.get("due_at")),
    )
    db.add(task)
    db.flush()
    ref_put(db, "reverify", task.task_id, "task", task.task_id, payload=payload.get("criteria"))
    db.commit()

    emit_event("reverify.due", {
        "reverify_id": task.task_id,
        "passport_id": exp.experiment_id,
        "assignee": payload.get("assignee"),
        "due_at": payload.get("due_at"),
    }, idempotency_key=f"reverify.due:{task.task_id}")

    return {"reverify_id": task.task_id, "task_id": task.task_id}
