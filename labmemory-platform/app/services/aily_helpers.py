"""Aily 集成 helpers（MCP tools 与 /v1/* HTTP 接口共享的业务内核）。

抽离自 `app/api/aily.py`，让 MCP Server 工具与 HTTP 端点走同一份业务逻辑，
避免双份实现漂移。所有函数都是无 HTTP 依赖的纯函数/会话作用域函数。

调用方：
- `app/api/aily.py`：10 个 `/v1/*` 入站 endpoint
- `app/mcp_server/tools.py`：10 个 `@mcp.call_tool()` 工具
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import new_id
from app.db.models import (
    AuditEvent,
    Candidate,
    Experiment,
    IntegrationRef,
    Meeting,
    MeetingReview,
    Task,
    User,
)


# === ID 映射 helpers（HTTP / MCP 共用）===

def ref_put(
    db: Session,
    ref_type: str,
    aily_id: str,
    platform_type: str,
    platform_id: str,
    payload: dict | None = None,
) -> IntegrationRef:
    """幂等写入 Aily↔平台实体映射；同 (ref_type, aily_id) 已存在则更新 platform_* 字段。"""
    row = (
        db.query(IntegrationRef)
        .filter(IntegrationRef.ref_type == ref_type, IntegrationRef.aily_id == aily_id)
        .first()
    )
    if row is None:
        row = IntegrationRef(
            ref_type=ref_type,
            aily_id=aily_id,
            platform_type=platform_type,
            platform_id=platform_id,
            payload=payload,
        )
        db.add(row)
    else:
        row.platform_type = platform_type
        row.platform_id = platform_id
        if payload is not None:
            row.payload = payload
    db.flush()
    return row


def ref_get(db: Session, ref_type: str, aily_id: str) -> IntegrationRef | None:
    return (
        db.query(IntegrationRef)
        .filter(IntegrationRef.ref_type == ref_type, IntegrationRef.aily_id == aily_id)
        .first()
    )


def meeting_from_ref(db: Session, ref_type: str, aily_id: str) -> Meeting | None:
    """通过 ref 找 meeting；ref 不存在时回退按 aily_id 当作 meeting_id 直接查。"""
    r = ref_get(db, ref_type, aily_id)
    mid = r.platform_id if r else aily_id
    return db.query(Meeting).filter(Meeting.meeting_id == mid).first()


def platform_id_from_ref(db: Session, ref_type: str, platform_id: str) -> str:
    """反查：platform_id → aily_id（ref 缺失时原样返回）。"""
    r = (
        db.query(IntegrationRef)
        .filter(IntegrationRef.ref_type == ref_type, IntegrationRef.platform_id == platform_id)
        .first()
    )
    return r.aily_id if r else platform_id


# === 实验/用户解析 ===

def experiment(db: Session, exp_id: str) -> Experiment:
    exp = db.query(Experiment).filter(Experiment.experiment_id == exp_id).first()
    if exp is None:
        raise NotFoundError(f"实验不存在：{exp_id}")
    return exp


def resolve_actor(db: Session, reviewer: str | None) -> User | None:
    """按 username 或 feishu_user_id 解析 User；不命中回退 PI（保证责任门可过）。"""
    if reviewer:
        u = (
            db.query(User)
            .filter((User.username == reviewer) | (User.feishu_user_id == reviewer))
            .first()
        )
        if u is not None:
            return u
    return db.query(User).filter(User.global_role == "pi").first()


# === 工具 ===

def parse_dt(v: Any) -> datetime | None:
    """ISO 字符串 → aware datetime；已为 datetime 或空/非法返回 None。"""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def jump_url(route: str) -> str:
    """前端 SPA 路由路径（生产由前端 base 拼接；与 HTTP 端点返回一致）。"""
    return f"{route}"


def build_candidates(db: Session, exp: Experiment, payload: dict) -> list[dict]:
    """从 Aily 抽取 payload 构造 Candidate.candidates JSON 字段。"""
    params = payload.get("params") or []
    out: list[dict] = []
    if params:
        out.append(
            {
                "candidate_id": payload.get("candidate_id") or new_id("CDR"),
                "type": "parameter_change",
                "title": payload.get("title") or "参数变更",
                "description": payload.get("summary") or "",
                "experiment_ref": exp.experiment_id,
                "parameters": params if isinstance(params, list) else [],
                "scope": payload.get("scope"),
                "confidence": payload.get("confidence") if payload.get("confidence") is not None else 0.9,
                "evidence": payload.get("evidence") or [],
                "status": "pending_review",
                "needs_review": True,
            }
        )
    for tc in payload.get("task_candidates") or []:
        if isinstance(tc, dict):
            out.append(
                {
                    "candidate_id": tc.get("candidate_id") or new_id("CDR"),
                    "type": "action_item",
                    "title": tc.get("title") or tc.get("name") or "行动项",
                    "description": tc.get("description") or "",
                    "experiment_ref": exp.experiment_id,
                    "parameters": [],
                    "confidence": 0.8,
                    "evidence": [],
                    "status": "pending_review",
                    "needs_review": True,
                }
            )
    return out


def candidate_ids(db: Session, meeting: Meeting) -> list[str]:
    """返回该会议下候选包的 candidate_id 列表（给 MCP 精简返回用）。"""
    cand = db.query(Candidate).filter(Candidate.meeting_id == meeting.id).first()
    return [c.get("candidate_id") for c in (cand.candidates if cand else []) or []]


# === 决策确认（HTTP / MCP 共用） ===

def confirm_decision(
    db: Session,
    meeting: Meeting,
    review: MeetingReview,
    actor: User | None,
    comment: str | None,
):
    """复用 `approve` 路径：六道闸门 + 主张/任务生成 + 审计事件。

    返回 (claim, task, publish_status, gate, conflicts)；MCP 工具与 HTTP
    verdict endpoint 共用此函数，避免业务逻辑双份实现漂移。

    延迟 import 避免 app.services → app.api 提前耦合。
    """
    from app.services.trust_rules import detect_conflicts, pick_candidate, run_six_gates
    from app.api.meetings import _build_claim  # noqa: WPS437（共享业务内核）

    exp = db.get(Experiment, meeting.experiment_id)
    cand_row = db.query(Candidate).filter(Candidate.meeting_id == meeting.id).first()
    chosen = pick_candidate(cand_row)
    gate = run_six_gates(chosen, None, exp, actor)
    new_params = (chosen or {}).get("parameters") or []
    new_scope = (chosen or {}).get("scope")
    conflicts = detect_conflicts(db, exp.id, new_params, new_scope, actor)
    blocked_by_conflict = any(c.get("severity") == "high" for c in conflicts)
    publish_status = "pending_supplement" if blocked_by_conflict else gate["publish_status"]

    claim = _build_claim(db, meeting, exp, cand_row, None, publish_status=publish_status)
    db.add(claim)
    db.flush()

    task = None
    if publish_status == "current":
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

    review.status = "processed"
    review.decision = "confirmed"
    review.reviewer_id = actor.id if actor else None
    review.reviewed_at = datetime.now(timezone.utc)
    review.notes = comment
    db.add(
        AuditEvent(
            actor_id=actor.id if actor else None,
            action="aily.decision.pass",
            target_type="meeting",
            target_id=meeting.meeting_id,
            after={
                "claim_id": claim.claim_id,
                "task_id": task.task_id if task else None,
                "publish_status": publish_status,
            },
            reason=comment or "",
        )
    )
    ref_put(db, "version", claim.claim_id, "claim", claim.claim_id)
    return claim, task, publish_status, gate, conflicts


__all__ = [
    "ref_put",
    "ref_get",
    "meeting_from_ref",
    "platform_id_from_ref",
    "experiment",
    "resolve_actor",
    "parse_dt",
    "jump_url",
    "build_candidates",
    "candidate_ids",
    "confirm_decision",
]