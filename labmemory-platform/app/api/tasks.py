"""任务与行动前审计。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_member, require_pi_or_lead
from app.api.deps import ensure_experiment_member
from app.api.meetings import _claim_out
from app.core.errors import NotFoundError, StateTransitionError
from app.core.security import new_id
from app.db.models import ActionAudit, AuditEvent, Claim, Experiment, Meeting, Result, Task, User
from app.schemas import (
    ActionAuditOut,
    AuditCompareOut,
    TaskApproveIn,
    TaskOut,
    TaskResourcesIn,
    TaskStartIn,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = _get_task(db, task_id)
    ensure_experiment_member(db, t.experiment_id, user)
    exp = db.get(Experiment, t.experiment_id)
    return _task_out(t, _meeting_id(db, t), exp.experiment_id if exp else "")


@router.post("/{task_id}/audit", response_model=ActionAuditOut)
def run_audit(task_id: str, db: Session = Depends(get_db), user: User = Depends(require_member)):
    """行动前审计：五项检查返回三态（passed/needs_confirmation/blocked）。"""
    t = _get_task(db, task_id)
    exp = db.get(Experiment, t.experiment_id)
    ensure_experiment_member(db, exp.id, user)
    if t.status not in ("draft", "audited", "needs_confirmation", "blocked"):
        raise StateTransitionError(f"任务状态 {t.status} 不可审计")

    audit = db.query(ActionAudit).filter(ActionAudit.task_id == t.id).first()
    if audit is None:
        audit = ActionAudit(task_id=t.id, status="pending")
        db.add(audit)
        db.flush()

    checks = _run_checks(t, exp, db)
    audit.status = checks["overall"]
    audit.auditor_id = user.id
    audit.audited_at = datetime.now(timezone.utc)
    audit.checks = checks["items"]
    audit.result = {
        "overall": checks["overall"],
        "reasons": checks["reasons"],
        "confirmations": checks["confirmations"],
    }

    # 任务状态随审计结论流转
    if audit.status == "passed":
        t.status = "audited"
    elif audit.status == "blocked":
        t.status = "blocked"
    else:  # needs_confirmation
        t.status = "needs_confirmation"

    db.add(AuditEvent(
        actor_id=user.id, action=f"task.audit.{audit.status}",
        target_type="task", target_id=t.task_id,
        after=audit.result, reason="; ".join(checks["reasons"] + checks["confirmations"]),
    ))
    db.commit()
    db.refresh(audit)
    return _audit_out(audit, t.task_id)


@router.post("/{task_id}/approve", response_model=TaskOut)
def approve_task(
    task_id: str,
    payload: TaskApproveIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_pi_or_lead),
):
    """审批通过（仅 PI/Lead）。审批门从 pending -> approved。"""
    t = _get_task(db, task_id)
    exp = db.get(Experiment, t.experiment_id)
    ensure_experiment_member(db, exp.id, user)
    if t.status in ("running", "completed"):
        raise StateTransitionError(f"任务已 {t.status}，不可审批")
    t.approval_status = "approved"
    t.approved_by = user.id
    t.approved_at = datetime.now(timezone.utc)
    t.approval_note = payload.note
    db.add(AuditEvent(
        actor_id=user.id, action="task.approved",
        target_type="task", target_id=t.task_id,
        after={"approval_status": "approved", "note": payload.note},
    ))
    db.commit()
    db.refresh(t)
    return _task_out(t, _meeting_id(db, t), exp.experiment_id)


@router.post("/{task_id}/reject", response_model=TaskOut)
def reject_task(
    task_id: str,
    payload: TaskApproveIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_pi_or_lead),
):
    """审批拒绝（仅 PI/Lead）。任务标记 blocked。"""
    t = _get_task(db, task_id)
    exp = db.get(Experiment, t.experiment_id)
    ensure_experiment_member(db, exp.id, user)
    if t.status in ("running", "completed"):
        raise StateTransitionError(f"任务已进入执行（{t.status}），不可拒绝审批")
    t.approval_status = "rejected"
    t.approved_by = user.id
    t.approved_at = datetime.now(timezone.utc)
    t.approval_note = payload.note
    t.status = "blocked"
    db.add(AuditEvent(
        actor_id=user.id, action="task.rejected",
        target_type="task", target_id=t.task_id,
        after={"approval_status": "rejected", "note": payload.note},
    ))
    db.commit()
    db.refresh(t)
    return _task_out(t, _meeting_id(db, t), exp.experiment_id)


@router.put("/{task_id}/resources", response_model=TaskOut)
def update_resources(
    task_id: str,
    payload: TaskResourcesIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
):
    """补充资源信息（物料/设备/排期/负责人），标记 resource_status=ready。"""
    t = _get_task(db, task_id)
    exp = db.get(Experiment, t.experiment_id)
    ensure_experiment_member(db, exp.id, user)
    resources: dict = {
        "materials": payload.materials,
        "equipment": payload.equipment,
        "scheduled_at": payload.scheduled_at.isoformat() if payload.scheduled_at else None,
        "note": payload.note,
    }
    if payload.assignee_username:
        assignee = db.query(User).filter(User.username == payload.assignee_username).first()
        if assignee is None:
            raise NotFoundError(f"用户不存在：{payload.assignee_username}")
        t.assignee_id = assignee.id
        resources["assignee"] = assignee.username
    t.resources = resources
    t.resource_status = "ready"
    if t.status == "needs_confirmation":
        t.status = "needs_confirmation"  # 保持，等重新审计
    db.add(AuditEvent(
        actor_id=user.id, action="task.resources_updated",
        target_type="task", target_id=t.task_id,
        after={"resource_status": "ready", "resource_count": len(payload.materials) + len(payload.equipment)},
    ))
    db.commit()
    db.refresh(t)
    return _task_out(t, _meeting_id(db, t), exp.experiment_id)


@router.post("/{task_id}/ack-failure-boundary", response_model=TaskOut)
def ack_failure_boundary(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
):
    """确认知晓历史失败边界风险（用户主动接受风险后，失败边界门通过）。"""
    t = _get_task(db, task_id)
    exp = db.get(Experiment, t.experiment_id)
    ensure_experiment_member(db, exp.id, user)
    t.failure_boundary_ack = True
    db.add(AuditEvent(
        actor_id=user.id, action="task.failure_boundary_acked",
        target_type="task", target_id=t.task_id,
        reason="用户确认知晓历史失败边界风险",
    ))
    db.commit()
    db.refresh(t)
    return _task_out(t, _meeting_id(db, t), exp.experiment_id)


@router.post("/{task_id}/start", response_model=TaskOut)
def start_task(task_id: str, payload: TaskStartIn, db: Session = Depends(get_db), user: User = Depends(require_member)):
    """审计通过后，PI/Lead/Executor 均可启动任务。"""
    t = _get_task(db, task_id)
    exp = db.get(Experiment, t.experiment_id)
    ensure_experiment_member(db, exp.id, user)
    audit = db.query(ActionAudit).filter(ActionAudit.task_id == t.id).first()
    if audit is None or audit.status != "passed":
        raise StateTransitionError("审计未通过，不能启动任务")
    if t.status != "audited":
        raise StateTransitionError(f"任务状态 {t.status} 不可启动（仅 audited 可启动；running 不可重复启动）")
    t.status = "running"
    if payload.assignee_username:
        assignee = db.query(User).filter(User.username == payload.assignee_username).first()
        if assignee is None:
            raise NotFoundError(f"用户不存在：{payload.assignee_username}")
        t.assignee_id = assignee.id
    else:
        t.assignee_id = user.id
    if payload.due_date:
        t.due_date = payload.due_date
    db.add(AuditEvent(
        actor_id=user.id, action="task.started",
        target_type="task", target_id=t.task_id,
        after={"assignee_id": t.assignee_id, "due_date": t.due_date.isoformat() if t.due_date else None},
    ))
    db.commit()
    db.refresh(t)
    return _task_out(t, _meeting_id(db, t), exp.experiment_id)


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(require_member)):
    """标记任务执行完成（进入结果回流阶段）。"""
    t = _get_task(db, task_id)
    exp = db.get(Experiment, t.experiment_id)
    ensure_experiment_member(db, exp.id, user)
    if t.status != "running":
        raise StateTransitionError(f"任务状态 {t.status} 不可完成")
    t.status = "completed"
    db.add(AuditEvent(
        actor_id=user.id, action="task.completed",
        target_type="task", target_id=t.task_id,
    ))
    db.commit()
    db.refresh(t)
    return _task_out(t, _meeting_id(db, t), exp.experiment_id)


@router.get("/{task_id}/audit/compare", response_model=AuditCompareOut)
def get_audit_compare(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """对比任务绑定的旧主张与实验当前主张，用于行动前审计阻断展示。"""
    t = _get_task(db, task_id)
    ensure_experiment_member(db, t.experiment_id, user)
    exp = db.get(Experiment, t.experiment_id)
    mt = db.get(Meeting, t.meeting_id)
    old_claim = db.get(Claim, t.claim_id) if t.claim_id else None
    current_claim = (
        db.query(Claim)
        .filter(Claim.experiment_id == exp.id, Claim.status == "current")
        .order_by(Claim.created_at.desc())
        .first()
    )
    is_blocked = bool(
        old_claim
        and current_claim
        and old_claim.id != current_claim.id
    )
    # 影响对象统计
    affected = {"tasks": 0, "results": 0, "meetings": 0}
    if is_blocked:
        affected["tasks"] = (
            db.query(Task)
            .filter(Task.experiment_id == exp.id, Task.claim_id == old_claim.id, Task.status.in_(["draft", "audited", "blocked"]))
            .count()
        )
        affected["meetings"] = (
            db.query(Meeting).filter(Meeting.experiment_id == exp.id).count()
        )
    audit = db.query(ActionAudit).filter(ActionAudit.task_id == t.id).first()
    return AuditCompareOut(
        task_id=t.task_id,
        meeting_id=mt.meeting_id if mt else "",
        experiment_id=exp.experiment_id,
        old_claim=_claim_out(old_claim, mt.meeting_id if mt else "", exp.experiment_id) if old_claim else None,
        current_claim=_claim_out(current_claim, "", exp.experiment_id) if current_claim else None,
        is_blocked=is_blocked,
        affected_objects=affected,
        recommended_action="replace_with_current_version" if is_blocked else None,
        task=_task_out(t, mt.meeting_id if mt else "", exp.experiment_id),
        audit=_audit_out(audit, t.task_id) if audit else None,
    )


@router.post("/{task_id}/audit/fix", response_model=TaskOut)
def audit_fix(task_id: str, db: Session = Depends(get_db), user: User = Depends(require_member)):
    """一键修正：用当前主张替换任务绑定的旧主张，生成新任务草稿。"""
    t = _get_task(db, task_id)
    exp = db.get(Experiment, t.experiment_id)
    ensure_experiment_member(db, exp.id, user)
    if t.status in ("running", "completed"):
        raise StateTransitionError(f"任务已进入执行（{t.status}），参数版本变更不影响进行中的任务，不可一键修正")
    current_claim = (
        db.query(Claim)
        .filter(Claim.experiment_id == exp.id, Claim.status == "current")
        .order_by(Claim.created_at.desc())
        .first()
    )
    if current_claim is None:
        raise StateTransitionError("实验当前无有效主张，无法修正")
    if t.claim_id == current_claim.id:
        raise StateTransitionError("任务已绑定当前主张，无需修正")
    # 重复修正守卫：同一会议已有一键修正生成的新任务则不重复
    existing_fix = db.query(Task).filter(
        Task.meeting_id == t.meeting_id,
        Task.claim_id == current_claim.id,
        Task.status != "blocked",
    ).first()
    if existing_fix:
        raise StateTransitionError(f"该任务已一键修正为新任务 {existing_fix.task_id}，无需重复修正")
    # 旧任务标记 blocked（保留历史）
    t.status = "blocked"
    # 新任务：同一会议，但绑定当前主张
    new_task = Task(
        task_id=new_id("T"),
        meeting_id=t.meeting_id,
        experiment_id=exp.id,
        claim_id=current_claim.id,
        status="draft",
        planned_params=current_claim.parameter_version,
        assignee_id=user.id,
    )
    db.add(new_task)
    db.flush()
    db.add(AuditEvent(
        actor_id=user.id, action="task.audit.fix",
        target_type="task", target_id=new_task.task_id,
        before={"old_task_id": t.task_id, "old_claim_id": t.claim_id},
        after={"new_claim_id": current_claim.id},
        reason="一键修正为当前参数版本",
    ))
    db.commit()
    db.refresh(new_task)
    return _task_out(new_task, _meeting_id(db, new_task), exp.experiment_id)


# === 内部 ===

def _get_task(db: Session, task_id: str) -> Task:
    t = db.query(Task).filter(Task.task_id == task_id).first()
    if t is None:
        raise NotFoundError(f"任务不存在：{task_id}")
    return t


def _meeting_id(db: Session, t: Task) -> str:
    from app.db.models import Meeting
    m = db.get(Meeting, t.meeting_id)
    return m.meeting_id if m else ""


def _task_out(t: Task, meeting_id: str, experiment_id: str) -> TaskOut:
    return TaskOut(
        id=t.id,
        task_id=t.task_id,
        meeting_id=meeting_id,
        experiment_id=experiment_id,
        claim_id=t.claim_id,
        status=t.status,
        assignee_id=t.assignee_id,
        due_date=t.due_date,
        planned_params=t.planned_params,
        approval_status=t.approval_status,
        approved_by=t.approved_by,
        approved_at=t.approved_at,
        approval_note=t.approval_note,
        resource_status=t.resource_status,
        resources=t.resources,
        failure_boundary_ack=t.failure_boundary_ack,
    )


def _audit_out(a: ActionAudit, task_id: str) -> ActionAuditOut:
    return ActionAuditOut(
        id=a.id,
        task_id=task_id,
        status=a.status,
        auditor_id=a.auditor_id,
        audited_at=a.audited_at,
        checks=a.checks,
        result=a.result,
    )


def _run_checks(t: Task, exp: Experiment, db: Session) -> dict:
    """五项检查：版本/证据/审批/资源/失败边界，返回三态结论。

    每项 status: passed / needs_confirmation / blocked
    overall 优先级：blocked > needs_confirmation > passed

    - 版本门（高风险）：旧版本引用 -> blocked
    - 证据门（高风险）：缺 scope/parameters -> blocked
    - 审批门：rejected -> blocked；pending -> needs_confirmation；approved -> passed
    - 资源门：未确认 -> needs_confirmation；ready -> passed
    - 失败边界门：存在未解决失败边界 -> needs_confirmation
    """
    items: dict[str, dict] = {}
    reasons: list[str] = []          # blocked 原因
    confirmations: list[str] = []    # needs_confirmation 原因

    # 1) 版本与单位：任务引用的 claim 必须是实验当前 current 主张
    from app.db.models import Claim
    task_claim = db.get(Claim, t.claim_id) if t.claim_id else None
    current_claim = (
        db.query(Claim)
        .filter(Claim.experiment_id == exp.id, Claim.status == "current")
        .order_by(Claim.created_at.desc())
        .first()
    )
    if task_claim is None:
        items["version_unit"] = {"status": "blocked", "reason": "任务未绑定主张"}
        reasons.append("版本门：任务未绑定主张")
    elif current_claim is None:
        items["version_unit"] = {"status": "blocked", "reason": "实验当前无有效（current）主张"}
        reasons.append("版本门：实验当前无 current 主张")
    elif task_claim.id != current_claim.id:
        items["version_unit"] = {
            "status": "blocked",
            "reason": f"任务引用 {task_claim.claim_id}({task_claim.status})；当前有效为 {current_claim.claim_id}",
            "old_claim_id": task_claim.claim_id,
            "current_claim_id": current_claim.claim_id,
        }
        reasons.append(f"版本门：旧版本 {task_claim.claim_id} 已被 {current_claim.claim_id} 替代")
    else:
        pv = t.planned_params or {}
        version = pv.get("version")
        items["version_unit"] = {"status": "passed", "version": version, "claim_id": task_claim.claim_id if task_claim else None}

    # 2) 证据与范围：参数是否有 evidence 与 scope
    pv = t.planned_params or {}
    evidence_ok = bool(pv.get("scope") or pv.get("parameters"))
    if not evidence_ok:
        items["evidence_scope"] = {"status": "blocked", "reason": "缺少 scope 或 parameters"}
        reasons.append("证据/范围门：缺少 scope 或 parameters")
    else:
        items["evidence_scope"] = {"status": "passed", "reason": None}

    # 3) 审批门：approval_status
    if t.approval_status == "approved":
        items["approval"] = {
            "status": "passed",
            "reason": f"已由 user_id={t.approved_by} 审批通过",
            "approved_by": t.approved_by,
            "approved_at": t.approved_at.isoformat() if t.approved_at else None,
        }
    elif t.approval_status == "rejected":
        items["approval"] = {"status": "blocked", "reason": "审批已被拒绝"}
        reasons.append("审批门：任务已被 PI/Lead 拒绝")
    else:
        items["approval"] = {"status": "needs_confirmation", "reason": "等待 PI/Lead 审批"}
        confirmations.append("审批门：任务尚未审批，请 PI/Lead 确认")

    # 4) 资源门：resource_status
    if t.resource_status == "ready":
        res = t.resources or {}
        items["resource"] = {
            "status": "passed",
            "reason": "资源已确认",
            "materials": len(res.get("materials") or []),
            "equipment": len(res.get("equipment") or []),
        }
    else:
        items["resource"] = {"status": "needs_confirmation", "reason": "资源未确认，请补充物料/设备/排期信息"}
        confirmations.append("资源门：物料/设备未确认，请补充后重新审计")

    # 5) 失败边界门：查询同实验已发布结果的 failure_boundary，未解决的需确认
    boundaries = _query_unresolved_failure_boundaries(db, exp.id)
    if boundaries and not t.failure_boundary_ack:
        items["failure_boundary"] = {
            "status": "needs_confirmation",
            "reason": f"存在 {len(boundaries)} 个未解决失败边界，请确认是否继续",
            "boundaries": boundaries,
            "acked": False,
        }
        confirmations.append(f"失败边界门：{len(boundaries)} 个未解决失败边界待确认")
    else:
        items["failure_boundary"] = {
            "status": "passed",
            "reason": "已确认" if boundaries else "无未解决失败边界",
            "boundaries": boundaries,
            "acked": t.failure_boundary_ack,
        }

    # overall: blocked > needs_confirmation > passed
    statuses = [i["status"] for i in items.values()]
    if "blocked" in statuses:
        overall = "blocked"
    elif "needs_confirmation" in statuses:
        overall = "needs_confirmation"
    else:
        overall = "passed"
    return {"overall": overall, "items": items, "reasons": reasons, "confirmations": confirmations}


def _query_unresolved_failure_boundaries(db: Session, experiment_id: int) -> list[dict]:
    """查询同实验下已发布结果的失败边界卡，筛选未解决的。

    未解决定义：root_cause_status 不是"已解决"/"resolved"/"已闭环"。
    """
    results = (
        db.query(Result, Task)
        .join(Task, Task.id == Result.task_id)
        .filter(Task.experiment_id == experiment_id, Result.status == "published")
        .all()
    )
    out: list[dict] = []
    for r, tk in results:
        fb = r.failure_boundary
        if not fb:
            continue
        root_status = (fb.get("root_cause_status") or "").strip()
        if root_status in ("已解决", "resolved", "已闭环", "closed"):
            continue
        out.append({
            "result_id": r.result_id,
            "task_id": tk.task_id,
            "phenomenon": fb.get("phenomenon"),
            "trigger_condition": fb.get("trigger_condition"),
            "root_cause_status": root_status or "待验证",
            "next_step": fb.get("next_step"),
        })
    return out
