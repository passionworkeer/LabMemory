"""可信知识问答 RAG 入口 + 会话生命周期管理。

按 PRD 8.6 与 decision-qa 规格实现：
- 权限前置过滤（按实验成员关系）
- 混合检索（结构化条件 + BM25 + 向量 + 关系扩展 + 重排）
- 状态与版本过滤（默认优先 current / supported / partially_supported）
- 大模型归纳生成（DeepSeek-V4-Flash，可降级到模板，支持多轮历史上下文）
- 带出处回答
- 无可靠证据时明确拒答
- 会话级历史持久化（按 user_id 隔离，刷新可回放）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.core.errors import NotFoundError, PermissionDeniedError
from app.db.models import QAMessage, QASession, User
from app.schemas import (
    QAAnswerOut,
    QAAskIn,
    QASessionDetailOut,
    QASessionOut,
    QASessionPatchIn,
)
from app.services import rag

router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.post("/ask", response_model=QAAnswerOut)
def ask(payload: QAAskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # 向量检索不可用时，rag.ask 自动降级为 BM25 + 关系扩展 + 重排
    # （retrieval_details.vector_available=false），不再返回 503（decision-qa 降级规格）。
    result = rag.ask(db, user, payload.question, payload.session_id, payload.session_title)
    return QAAnswerOut(**result)


@router.get("/sessions", response_model=list[QASessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=settings.QA_SESSION_LIST_DEFAULT_LIMIT, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_archived: bool = Query(default=False),
):
    q = select(QASession).where(QASession.user_id == user.id)
    if not include_archived:
        q = q.where(QASession.archived.is_(False))
    q = q.order_by(QASession.last_message_at.desc().nullslast(), QASession.id.desc()).limit(limit).offset(offset)
    sessions = db.execute(q).scalars().all()
    out: list[QASessionOut] = []
    for s in sessions:
        cnt = db.scalar(
            select(func.count(QAMessage.id)).where(QAMessage.session_id == s.id)
        ) or 0
        out.append(QASessionOut(id=s.id, title=s.title, archived=s.archived, last_message_at=s.last_message_at, message_count=int(cnt), created_at=s.created_at))
    return out


@router.get("/sessions/{session_id}", response_model=QASessionDetailOut)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_owned_session(db, user, session_id)
    msgs_q = (
        select(QAMessage)
        .where(QAMessage.session_id == session.id)
        .order_by(QAMessage.id.desc())
        .limit(settings.QA_SESSION_MAX_MESSAGES)
    )
    msgs = list(reversed(db.execute(msgs_q).scalars().all()))
    return QASessionDetailOut(
        id=session.id,
        title=session.title,
        archived=session.archived,
        last_message_at=session.last_message_at,
        created_at=session.created_at,
        messages=[
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "citations": m.citations_json,
                "refused": m.refused,
                "retrieval_details": m.retrieval_details_json,
                "model_info": m.model_info_json,
                "missing_conditions": m.missing_conditions_json,
                "created_at": m.created_at,
            }
            for m in msgs
        ],
    )


@router.patch("/sessions/{session_id}", response_model=QASessionOut)
def patch_session(
    session_id: int,
    payload: QASessionPatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_owned_session(db, user, session_id)
    if payload.title is not None:
        session.title = (payload.title.strip() or session.title)[:128]
    if payload.archived is not None:
        session.archived = payload.archived
    db.commit()
    cnt = db.scalar(
        select(func.count(QAMessage.id)).where(QAMessage.session_id == session.id)
    ) or 0
    return QASessionOut(
        id=session.id,
        title=session.title,
        archived=session.archived,
        last_message_at=session.last_message_at,
        message_count=int(cnt),
        created_at=session.created_at,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_owned_session(db, user, session_id)
    db.delete(session)  # ON DELETE CASCADE 级联清消息
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_owned_session(db: Session, user: User, session_id: int) -> QASession:
    session = db.get(QASession, session_id)
    if session is None:
        raise NotFoundError(f"会话不存在：{session_id}")
    if session.user_id != user.id:
        # 不区分 403/404，避免泄漏存在性
        raise PermissionDeniedError("无权访问该会话")
    return session
