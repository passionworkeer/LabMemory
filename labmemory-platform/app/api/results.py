"""结果回流。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    ensure_experiment_member,
    get_current_user,
    get_db,
    require_member,
    require_pi_or_lead,
)
from app.core.errors import NotFoundError, StateTransitionError
from app.core.security import new_id
from app.db.models import AuditEvent, Claim, Experiment, Result, Task, User
from app.schemas import ResultOut, ResultPublishIn, ResultSubmitIn

router = APIRouter(tags=["results"])


@router.post("/api/tasks/{task_id}/results", response_model=ResultOut)
def submit_result(
    task_id: str,
    payload: ResultSubmitIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
):
    """PI/Lead/Executor 均可提交实验结果。每个任务只能提交一次，且必须先启动任务。"""
    t = _get_task(db, task_id)
    exp = db.get(Experiment, t.experiment_id)
    ensure_experiment_member(db, exp.id, user)
    if t.status not in ("running", "completed"):
        raise StateTransitionError(f"任务状态 {t.status} 不可提交结果（需先启动任务）")

    # 防重复提交：每个任务只能有一条结果
    existing = db.query(Result).filter(Result.task_id == t.id).first()
    if existing:
        raise StateTransitionError(f"任务已提交过结果：{existing.result_id}（每个任务仅可提交一次）")

    # 冻结判定（结果版本校验）：实际参数必须覆盖全部计划参数名且值非空
    # （null/空串/纯空白 = 未如实记录，同样视为参数不匹配→冻结）；
    # 实际包含计划外的额外 key 不触发冻结（额外观测不算版本不匹配）
    planned = t.planned_params or {}
    planned_keys = {(p.get("name") if isinstance(p, dict) else None) for p in planned.get("parameters", [])} - {None}
    actual = payload.actual_params or {}

    def _filled(name: str) -> bool:
        v = actual.get(name)
        return v is not None and str(v).strip() != ""

    frozen = bool(planned_keys) and not all(_filled(k) for k in planned_keys)
    status = "frozen" if frozen else "submitted"

    res = Result(
        result_id=new_id("R"),
        task_id=t.id,
        submitter_id=user.id,
        actual_params=payload.actual_params,
        metrics=payload.metrics,
        files=payload.files,
        status=status,
        notes=payload.notes,
    )
    db.add(res)

    # 提交结果即视为任务执行完成（无需单独标记完成）
    task_completed = False
    if t.status != "completed":
        t.status = "completed"
        task_completed = True
        db.add(AuditEvent(
            actor_id=user.id, action="task.completed",
            target_type="task", target_id=t.task_id,
            reason="结果提交后自动完成",
        ))

    db.add(AuditEvent(
        actor_id=user.id, action=f"result.submitted.{status}",
        target_type="result", target_id=res.result_id,
        after={"task_id": t.task_id, "frozen": frozen, "task_auto_completed": task_completed},
    ))
    db.commit()
    db.refresh(res)
    return _result_out(res, t.task_id, t.planned_params)


@router.post("/api/results/{result_id}/publish", response_model=ResultOut)
def publish_result(
    result_id: str,
    payload: ResultPublishIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_pi_or_lead),
):
    """仅 PI/Lead 可将结果发布为知识。"""
    res = db.query(Result).filter(Result.result_id == result_id).first()
    if res is None:
        raise NotFoundError(f"结果不存在：{result_id}")
    if res.status == "published":
        raise StateTransitionError("结果已发布")
    if res.status == "frozen":
        raise StateTransitionError("结果已冻结，需先解决版本不匹配后再发布")
    t = db.get(Task, res.task_id)
    if t is None:
        raise NotFoundError(f"结果 {result_id} 关联任务不存在")
    exp = db.get(Experiment, t.experiment_id)
    if exp is None:
        raise NotFoundError(f"结果关联实验不存在")
    ensure_experiment_member(db, exp.id, user)

    # 证据失效降级（PRD §13.1）：关联主张证据失效时，仅允许 insufficient_evidence/refuted
    if t.claim_id:
        from app.db.models import Claim
        claim = db.get(Claim, t.claim_id)
        if claim is not None:
            from app.services.evidence import validate_evidence
            ev = validate_evidence(claim)
            if not ev["valid"] and payload.knowledge_status not in ("insufficient_evidence", "refuted"):
                raise StateTransitionError(
                    f"关联主张证据失效（{ev['reason']}），须采用 insufficient_evidence 或 refuted，不可标为 {payload.knowledge_status}"
                )

    res.status = "published"
    res.publisher_id = user.id
    res.published_at = datetime.now(timezone.utc)
    res.knowledge_status = payload.knowledge_status
    res.notes = payload.notes or res.notes
    if payload.failure_boundary:
        res.failure_boundary = payload.failure_boundary
    if payload.model_feedback:
        res.model_feedback = payload.model_feedback

    # 同步更新实验当前主张的知识验证状态（不影响生命周期 status）
    if t and t.claim_id:
        claim = db.get(Claim, t.claim_id)
        if claim and claim.status == "current":
            claim.knowledge_status = payload.knowledge_status

    # 标记任务完成（结果回流完成即会议任务结束）
    if t and t.status != "completed":
        t.status = "completed"

    db.add(AuditEvent(
        actor_id=user.id, action="result.published",
        target_type="result", target_id=res.result_id,
        after={"knowledge_status": payload.knowledge_status, "task_id": t.task_id if t else None},
    ))
    db.commit()
    db.refresh(res)

    # 索引新发布的结果与失败边界，供可信问答检索（失败不阻断业务，但必须留痕）
    try:
        from app.services.indexer import index_failure_boundary, index_result
        index_result(db, res)
        index_failure_boundary(db, res)
        # 若关联主张知识状态变化，重新索引该主张
        if t and t.claim_id:
            from app.db.models import Claim
            claim = db.get(Claim, t.claim_id)
            if claim and claim.status == "current":
                from app.services.indexer import index_claim
                index_claim(db, claim)
        db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "结果发布后检索索引更新失败（业务已提交，可经 admin 重建索引恢复）: %s", e
        )
        db.rollback()

    _request_publish_doc(db, t, res)
    return _result_out(res, t.task_id if t else "", t.planned_params if t else None)


# === 内部 ===

def _get_task(db: Session, task_id: str) -> Task:
    t = db.query(Task).filter(Task.task_id == task_id).first()
    if t is None:
        raise NotFoundError(f"任务不存在：{task_id}")
    return t


def _result_out(r: Result, task_id: str, planned_params: dict | None = None) -> ResultOut:
    return ResultOut(
        id=r.id,
        result_id=r.result_id,
        task_id=task_id,
        submitter_id=r.submitter_id,
        actual_params=r.actual_params,
        metrics=r.metrics,
        files=r.files,
        status=r.status,
        publisher_id=r.publisher_id,
        published_at=r.published_at,
        knowledge_status=r.knowledge_status,
        failure_boundary=r.failure_boundary,
        model_feedback=r.model_feedback,
        notes=r.notes,
        planned_params=planned_params,
    )


# === 反向联动（平台 → 飞书编排器，非阻断）===

def _request_publish_doc(db: Session, t: Task | None, res: Result) -> None:
    """知识发布后请求飞书侧发布知识文档（publish_doc），失败不阻断主业务。"""
    if t is None:
        return
    try:
        from app.db.models import Candidate, Meeting
        from app.services.feishu_client import actor_user_id_for, candidate_dict_from_candidates, send_feishu_action

        meeting = db.get(Meeting, t.meeting_id)
        cand_row = db.query(Candidate).filter(Candidate.meeting_id == t.meeting_id).first()
        candidate = candidate_dict_from_candidates(cand_row.candidates if cand_row else None)
        if candidate is None or meeting is None:
            return

        doc_type = {
            "supported": "success",
            "refuted": "failure",
            "partially_supported": "failure",
        }.get(res.knowledge_status, "pending")

        actor = db.get(User, res.publisher_id) if res.publisher_id else None
        send_feishu_action(
            action_type="publish_doc",
            actor_user_id=actor_user_id_for(actor),
            candidate_id=candidate.get("candidate_id"),
            payload={
                "candidate": candidate,
                "meeting_title": meeting.title,
                "doc_type": doc_type,
            },
            idempotency_key=f"publish_doc:{res.result_id}",
        )
    except Exception:  # noqa: BLE001
        pass
