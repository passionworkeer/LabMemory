"""可信知识问答（简化版：基于关键词的 Claim/Result 检索）。

按 PRD 要求：
- 权限前置过滤（按实验成员关系）
- 状态与版本过滤（默认优先 current / supported / partially_supported）
- 带出处回答
- 没有可靠证据时明确拒答
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import Claim, Experiment, Result, Task, User
from app.schemas import QAAnswerOut, QAAskIn

router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.post("/ask", response_model=QAAnswerOut)
def ask(payload: QAAskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = payload.question.strip().lower()
    if not q:
        return QAAnswerOut(
            question=payload.question,
            answer="问题为空，请输入有效问题。",
            refused=True,
            retrieval_scope={"reason": "empty_question"},
        )

    # 关键词切分（简单按空格/标点）
    keywords = [w for w in q.replace(",", " ").replace("?", " ").replace("？", " ").split() if w]
    if not keywords:
        keywords = [q]

    # 仅检索 user 可见的实验（PI 全量；其他角色需为成员）
    if user.global_role in ("admin", "pi"):
        exps = db.query(Experiment).all()
    else:
        from app.db.models import ExperimentMember
        exps = (
            db.query(Experiment)
            .join(ExperimentMember, ExperimentMember.experiment_id == Experiment.id)
            .filter(ExperimentMember.user_id == user.id)
            .all()
        )
    exp_ids = {e.id for e in exps}

    # 检索 current/supported/partially_supported 主张
    qs = (
        db.query(Claim)
        .filter(
            Claim.experiment_id.in_(exp_ids),
            Claim.status.in_(["current"]),
        )
        .order_by(Claim.created_at.desc())
    )
    matched: list[tuple[Claim, int]] = []
    for c in qs.all():
        text = _claim_text(c).lower()
        score = sum(1 for k in keywords if k in text)
        if score > 0:
            matched.append((c, score))
    matched.sort(key=lambda x: -x[1])

    if not matched:
        return QAAnswerOut(
            question=payload.question,
            answer="暂无满足证据和权限要求的可靠结论。请补充实验编号、参数名称或适用范围后重试。",
            refused=True,
            retrieval_scope={
                "identity": user.display_name,
                "searched_experiments": len(exp_ids),
                "status_filter": ["current"],
                "reason": "no_match",
            },
        )

    top = matched[0][0]
    exp = db.get(Experiment, top.experiment_id)
    # 取支持该主张的结果
    supporting_results = (
        db.query(Result)
        .join(Task, Task.id == Result.task_id)
        .filter(Task.experiment_id == top.experiment_id, Result.status == "published")
        .all()
    )
    citations = []
    for r in supporting_results[:3]:
        citations.append({
            "type": "result",
            "id": r.result_id,
            "knowledge_status": r.knowledge_status,
            "metrics": r.metrics,
        })
    # 加上主张本身的证据
    for ev in (top.content or {}).get("evidence", [])[:2]:
        citations.append({"type": "evidence", "speaker": ev.get("speaker"), "text": ev.get("text")})

    answer = (
        f"实验 {exp.experiment_id} 当前主张 {top.claim_id}（{top.knowledge_status or 'current'}）："
        f"{(top.content or {}).get('title', '')}。"
        f"参数版本 {(top.parameter_version or {}).get('version', '?')}，"
        f"参数列表：{', '.join(p.get('name','')+'='+p.get('value','') for p in (top.parameter_version or {}).get('parameters', []))}。"
    )

    return QAAnswerOut(
        question=payload.question,
        answer=answer,
        citations=citations,
        retrieval_scope={
            "identity": user.display_name,
            "searched_experiments": len(exp_ids),
            "status_filter": ["current"],
            "matched_claims": len(matched),
            "top_score": matched[0][1],
        },
    )


def _claim_text(c: Claim) -> str:
    parts = [(c.content or {}).get("title", ""), (c.content or {}).get("description", "")]
    for p in (c.parameter_version or {}).get("parameters", []) or []:
        parts.append(f"{p.get('name','')} {p.get('value','')} {p.get('unit','')}")
    for ev in (c.content or {}).get("evidence", []) or []:
        parts.append(ev.get("text", ""))
    return " ".join(parts)
