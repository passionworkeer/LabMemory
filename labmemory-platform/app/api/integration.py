"""飞书编排器集成路由（/api/v1 契约侧）。

挂载契约要求的 3 条平台→编排器侧路由（候选提交在 meetings.v1_router）：
  GET  /api/v1/candidates/{candidate_id}  候选详情（扁平 + 富化）
  POST /api/v1/task/status                回写飞书任务状态
  POST /api/v1/card/callback              转发卡片回调（嵌套信封，按 action_type 分流）

鉴权与 meetings.v1_router 一致：verify_platform_api_key（双接受 Bearer / X-Platform-Api-Key）。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, verify_platform_api_key
from app.core.errors import NotFoundError
from app.core.security import new_id
from app.db.models import (
    ActionAudit,
    AuditEvent,
    Candidate,
    Claim,
    Experiment,
    Meeting,
    MeetingReview,
    Task,
    User,
)
from app.schemas import CardCallbackIn, TaskStatusIn

router = APIRouter(prefix="/api/v1", tags=["integration"], dependencies=[Depends(verify_platform_api_key)])


# === 解析 helper ===

def _resolve_candidate(db: Session, candidate_id: str):
    """candidate_id → (Meeting, Candidate 行, candidate dict)。扫 Candidate.candidates JSON。

    demo 规模 O(候选总数) 可接受；生产规模可加 candidate_id 索引列（另起 change）。
    """
    for row in db.query(Candidate).all():
        for c in (row.candidates or []):
            if c.get("candidate_id") == candidate_id:
                meeting = db.get(Meeting, row.meeting_id)
                return meeting, row, c
    return None, None, None


def _actor_for(db: Session, open_id: str | None) -> User | None:
    """open_id → 平台 User（feishu_user_id）；无映射返 None——不充当 admin，审计 reason 记原始 open_id。"""
    if open_id:
        return db.query(User).filter(User.feishu_user_id == open_id).first()
    return None


# === 路由 ===

@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    """候选详情（扁平对象，富化 meeting_title / source_url，供编排器构建飞书任务摘要）。"""
    meeting, _row, cand = _resolve_candidate(db, candidate_id)
    if cand is None:
        raise NotFoundError(f"候选不存在：{candidate_id}")
    return {
        "candidate_id": cand.get("candidate_id"),
        "type": cand.get("type"),
        "title": cand.get("title"),
        "description": cand.get("description"),
        "experiment_ref": cand.get("experiment_ref"),
        "parameters": cand.get("parameters", []),
        "evidence": cand.get("evidence", []),
        "confidence": cand.get("confidence"),
        "status": cand.get("status"),
        "needs_review": cand.get("needs_review"),
        "assignee": cand.get("assignee"),
        "due_date": cand.get("due_date"),
        "meeting_title": meeting.title if meeting else None,
        "source_url": meeting.source_url if meeting else None,
    }


@router.post("/task/status")
def update_task_status(payload: TaskStatusIn, db: Session = Depends(get_db)):
    """回写飞书任务状态：candidate_id → 会议最新任务，写 feishu_task_guid。"""
    meeting, _row, _cand = _resolve_candidate(db, payload.candidate_id)
    if meeting is None:
        raise NotFoundError(f"候选不存在：{payload.candidate_id}")
    task = (
        db.query(Task)
        .filter(Task.meeting_id == meeting.id)
        .order_by(Task.id.desc())
        .first()
    )
    if task is None:
        raise NotFoundError(f"候选 {payload.candidate_id} 对应会议无任务")

    if payload.feishu_task_guid:
        task.feishu_task_guid = payload.feishu_task_guid
    if payload.status == "failed" and payload.error:
        db.add(AuditEvent(
            action="task.feishu_failed",
            target_type="task",
            target_id=task.task_id,
            reason=payload.error,
            after={"status": "failed", "error": payload.error},
        ))
    db.commit()
    return {"ok": True, "task_id": task.task_id, "feishu_task_guid": task.feishu_task_guid}


@router.post("/card/callback")
def card_callback(payload: CardCallbackIn, db: Session = Depends(get_db)):
    """转发卡片回调：解析嵌套飞书信封，按 action_type 分流，返回 {status, action_audit, candidate_id, message}。

    action_audit 取真实六道闸门审计结论（passed→"pass"），不乐观放行。
    """
    from app.api.meetings import _build_claim  # lazy，沿用既有 _chain_item 跨模块复用模式
    from app.api.tasks import _run_checks

    token = payload.token
    action_type = payload.action.value.action_type
    candidate_id = payload.action.value.candidate_id

    # 幂等：同 token 已处理 → 返回上次结论
    prior = (
        db.query(AuditEvent)
        .filter(AuditEvent.action == "card_callback", AuditEvent.target_id == token)
        .order_by(AuditEvent.id.desc())
        .first()
    )
    if prior and prior.after:
        return {**prior.after, "candidate_id": candidate_id}

    actor = _actor_for(db, payload.open_id)
    actor_id = actor.id if actor else None

    meeting, cand_row, _cand = _resolve_candidate(db, candidate_id)
    if meeting is None:
        resp = {"status": "blocked", "action_audit": "unknown_candidate",
                "candidate_id": candidate_id, "message": f"候选不存在：{candidate_id}"}
        _log_callback(db, token, action_type, candidate_id, resp, actor_id)
        db.commit()
        return resp

    exp = db.get(Experiment, meeting.experiment_id)
    review = db.query(MeetingReview).filter(MeetingReview.meeting_id == meeting.id).first()

    if action_type == "reject":
        if review and review.status == "pending":
            review.status = "processed"
            review.decision = "ended"
            review.reviewer_id = actor_id
            review.reviewed_at = datetime.utcnow()
        resp = {"status": "rejected", "action_audit": "reject", "candidate_id": candidate_id,
                "message": "已驳回，会议不进入数据链路"}
        _log_callback(db, token, action_type, candidate_id, resp, actor_id)
        db.commit()
        return resp

    if action_type == "revise":
        resp = {"status": "blocked", "action_audit": "revise", "candidate_id": candidate_id,
                "message": "卡片未携带修改内容，请到平台前端修改后再确认"}
        _log_callback(db, token, action_type, candidate_id, resp, actor_id)
        db.commit()
        return resp

    # action_type == "approve"：复核确认 → 生成主张/任务草稿 → 六道闸门审计
    task = None
    if review and review.status == "pending":
        review.status = "processed"
        review.decision = "confirmed"
        review.reviewer_id = actor_id
        review.reviewed_at = datetime.utcnow()
        claim = _build_claim(db, meeting, exp, cand_row, None)
        db.add(claim)
        db.flush()
        task = Task(
            task_id=new_id("T"),
            meeting_id=meeting.id,
            experiment_id=exp.id,
            claim_id=claim.id,
            status="draft",
            planned_params=claim.parameter_version,
        )
        db.add(task)
        db.flush()
    else:
        task = (
            db.query(Task)
            .filter(Task.meeting_id == meeting.id)
            .order_by(Task.id.desc())
            .first()
        )
        # 复核已 processed：仅 draft/needs_confirmation/blocked 可重审；running/completed 不回退状态
        if task is not None and task.status not in ("draft", "needs_confirmation", "blocked"):
            existing_audit = db.query(ActionAudit).filter(ActionAudit.task_id == task.id).first()
            aa = existing_audit.status if existing_audit else "needs_confirmation"
            resp = {
                "status": "approved" if aa == "passed" else "blocked",
                "action_audit": aa,
                "candidate_id": candidate_id,
                "message": f"任务已 {task.status}，不重新审计（避免状态回退）",
            }
            _log_callback(db, token, action_type, candidate_id, resp, actor_id, task_id=task.task_id)
            db.commit()
            return resp

    if task is None:
        resp = {"status": "blocked", "action_audit": "no_task", "candidate_id": candidate_id,
                "message": "会议尚未生成任务"}
        _log_callback(db, token, action_type, candidate_id, resp, actor_id)
        db.commit()
        return resp

    # 六道闸门审计
    audit = db.query(ActionAudit).filter(ActionAudit.task_id == task.id).first()
    if audit is None:
        audit = ActionAudit(task_id=task.id, status="pending")
        db.add(audit)
        db.flush()
    checks = _run_checks(task, exp, db)
    audit.status = checks["overall"]
    audit.auditor_id = actor_id
    audit.audited_at = datetime.utcnow()
    audit.checks = checks["items"]
    audit.result = {
        "overall": checks["overall"],
        "reasons": checks["reasons"],
        "confirmations": checks["confirmations"],
    }
    if audit.status == "passed":
        task.status = "audited"
    elif audit.status == "blocked":
        task.status = "blocked"
    else:
        task.status = "needs_confirmation"

    # 映射到编排器词汇：passed → action_audit="pass"（card_handler.py:57 的硬门控）
    if audit.status == "passed":
        action_audit, status, message = "pass", "approved", "六道闸门审计通过，可创建飞书任务"
    elif audit.status == "blocked":
        action_audit, status, message = "block", "blocked", "行动前审计阻断：" + "; ".join(checks["reasons"])
    else:
        action_audit, status, message = "needs_confirmation", "blocked", "需确认：" + "; ".join(checks["confirmations"])

    resp = {"status": status, "action_audit": action_audit, "candidate_id": candidate_id, "message": message}
    _log_callback(db, token, action_type, candidate_id, resp, actor_id, task_id=task.task_id)
    db.commit()
    return resp


def _log_callback(
    db: Session,
    token: str,
    action_type: str,
    candidate_id: str,
    resp: dict,
    actor_id: int | None,
    task_id: str | None = None,
) -> None:
    after = {k: v for k, v in resp.items() if k != "candidate_id"}
    db.add(AuditEvent(
        actor_id=actor_id,
        action="card_callback",
        target_type="candidate",
        target_id=token,
        after=after,
        reason=f"{action_type} candidate={candidate_id}" + (f" task={task_id}" if task_id else ""),
    ))
