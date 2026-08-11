"""可信知识问答 RAG 入口。

按 PRD 8.6 要求实现：
- 权限前置过滤（按实验成员关系）
- 混合检索（结构化条件 + BM25 + 向量 + 关系扩展 + 重排）
- 状态与版本过滤（默认优先 current / supported / partially_supported）
- 大模型归纳生成（DeepSeek-V4-Flash，可降级到模板）
- 带出处回答
- 无可靠证据时明确拒答
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db import vec
from app.db.models import User
from app.schemas import QAAnswerOut, QAAskIn
from app.services import rag

router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.post("/ask", response_model=QAAnswerOut)
def ask(payload: QAAskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # 向量扩展不可用时返回 503，提示安装 sqlite-vec
    if not vec.vec_available(db):
        raise HTTPException(
            status_code=503,
            detail="向量检索扩展不可用，请安装 sqlite-vec（pip install sqlite-vec）后重启服务。",
        )
    result = rag.ask(db, user, payload.question)
    return QAAnswerOut(**result)
