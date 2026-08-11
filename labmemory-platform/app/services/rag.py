"""RAG 编排器：权限前置过滤 -> 状态过滤 -> BM25+向量召回 -> 关系扩展 -> 重排 -> LLM 生成 -> 引用后处理。"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db import vec
from app.db.models import (
    Claim,
    EmbeddingChunk,
    Experiment,
    ExperimentMember,
    Result,
    Task,
    User,
)
from app.services.embedding import get_embedding_service
from app.services.indexer import ensure_index_ready
from app.services.llm import detect_refusal, extract_citation_refs, get_llm_service


STATUS_WEIGHT = {
    "supported": 1.0,
    "partially_supported": 0.7,
    None: 0.5,
    "refuted": 0.2,
}


def _user_experiments(db: Session, user: User) -> list[int]:
    """返回用户可见的 experiment id 列表。"""
    if user.global_role in ("admin", "pi"):
        return [e.id for e in db.query(Experiment).all()]
    rows = (
        db.query(Experiment.id)
        .join(ExperimentMember, ExperimentMember.experiment_id == Experiment.id)
        .filter(ExperimentMember.user_id == user.id)
        .all()
    )
    return [r[0] for r in rows]


def _candidate_chunk_ids(
    db: Session, exp_ids: list[int]
) -> tuple[list[str], list[EmbeddingChunk]]:
    """状态过滤：返回符合状态条件的 chunk_id 列表与 chunk 对象。"""
    if not exp_ids:
        return [], []
    # claim: status='current' AND knowledge_status IN (null, supported, partially_supported)
    # result: status='published' AND knowledge_status IN (null, supported, partially_supported)
    # evidence/boundary: status='active'/'published'（无 knowledge_status 过滤）
    chunks = (
        db.query(EmbeddingChunk)
        .filter(EmbeddingChunk.experiment_id.in_(exp_ids))
        .filter(
            (
                (EmbeddingChunk.chunk_type == "claim")
                & (EmbeddingChunk.status == "current")
                & (EmbeddingChunk.knowledge_status.in_([None, "supported", "partially_supported"]))
            )
            | (
                (EmbeddingChunk.chunk_type == "result")
                & (EmbeddingChunk.status == "published")
                & (EmbeddingChunk.knowledge_status.in_([None, "supported", "partially_supported"]))
            )
            | (EmbeddingChunk.chunk_type == "evidence")
            | (EmbeddingChunk.chunk_type == "failure_boundary")
        )
        .all()
    )
    return [c.chunk_id for c in chunks], chunks


def _relation_expand(db: Session, hit_chunks: list[EmbeddingChunk], all_chunks_by_id: dict[str, EmbeddingChunk]) -> list[str]:
    """对命中的 claim chunk，拉取其支持结果与证据片段，返回新增 chunk_id 列表。"""
    extra_ids: list[str] = []
    for c in hit_chunks:
        if c.chunk_type != "claim":
            continue
        claim = db.query(Claim).filter(Claim.claim_id == c.ref_id).first()
        if not claim:
            continue
        # 关联结果：通过 Task.claim_id -> Result.task_id
        tasks = db.query(Task).filter(Task.claim_id == claim.id).all()
        if tasks:
            task_ids = [t.id for t in tasks]
            results = (
                db.query(Result)
                .filter(Result.task_id.in_(task_ids), Result.status == "published")
                .all()
            )
            for r in results:
                cid = f"result:{r.result_id}"
                if cid in all_chunks_by_id:
                    extra_ids.append(cid)
                if r.failure_boundary:
                    bid = f"boundary:{r.result_id}"
                    if bid in all_chunks_by_id:
                        extra_ids.append(bid)
        # 关联证据：通过 claim.meeting_id -> Meeting.transcript 切片
        meeting = db.query(EmbeddingChunk).filter(
            EmbeddingChunk.chunk_type == "evidence",
            EmbeddingChunk.ref_id.like(f"{claim.meeting_id}#%"),
        ).first()
        # 仅取第一条证据作为代表
        if meeting:
            extra_ids.append(meeting.chunk_id)
    return extra_ids


def _recency_score(chunk: EmbeddingChunk) -> float:
    """时间新鲜度：基于 updated_at 距今天数，越新得分越高（0~1）。"""
    ts = chunk.updated_at or chunk.created_at
    if not ts:
        return 0.5
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    days = max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0)
    return math.exp(-days / 30.0)  # 30 天半衰期


def _rerank(
    candidates: list[EmbeddingChunk],
    bm25_scores: dict[str, float],
    vec_scores: dict[str, float],
) -> list[tuple[EmbeddingChunk, float, dict]]:
    """融合排序。返回 [(chunk, total_score, score_breakdown), ...] 取 top K。"""
    if not candidates:
        return []
    # 归一化 BM25 与向量分数到 0~1
    bm25_max = max(bm25_scores.values()) if bm25_scores else 0.0
    bm25_max = max(bm25_max, 1e-9)
    vec_max = max(vec_scores.values()) if vec_scores else 0.0
    vec_max = max(vec_max, 1e-9)

    scored: list[tuple[EmbeddingChunk, float, dict]] = []
    for c in candidates:
        bm25_norm = bm25_scores.get(c.chunk_id, 0.0) / bm25_max
        vec_norm = vec_scores.get(c.chunk_id, 0.0) / vec_max
        recency = _recency_score(c)
        status_w = STATUS_WEIGHT.get(c.knowledge_status, 0.5)
        # chunk_type 偏置：claim > result > boundary > evidence
        type_w = {"claim": 1.0, "result": 0.85, "failure_boundary": 0.7, "evidence": 0.6}.get(
            c.chunk_type, 0.5
        )
        total = (
            settings.RAG_BM25_WEIGHT * bm25_norm
            + settings.RAG_VECTOR_WEIGHT * vec_norm
            + settings.RAG_RECENCY_WEIGHT * recency
            + settings.RAG_STATUS_WEIGHT * status_w
        ) * type_w
        scored.append(
            (
                c,
                total,
                {
                    "bm25": round(bm25_norm, 4),
                    "vector": round(vec_norm, 4),
                    "recency": round(recency, 4),
                    "status": round(status_w, 4),
                    "type": round(type_w, 4),
                    "total": round(total, 4),
                },
            )
        )
    scored.sort(key=lambda x: -x[1])
    return scored[: settings.RAG_TOP_K]


def _lookup_task_id(db: Session, result_id: str) -> str | None:
    """通过 result_id 查询关联的 task_id（字符串形式），用于生成 result 详情页 URL。"""
    result = db.query(Result).filter(Result.result_id == result_id).first()
    if not result:
        return None
    task = db.get(Task, result.task_id)
    return task.task_id if task else None


def _build_citation(chunk: EmbeddingChunk, ref_label: str, db: Session) -> dict:
    """从 chunk 构造结构化引用对象。"""
    meta = chunk.metadata_json or {}
    exp_id = meta.get("experiment_id", "")
    meeting_id = meta.get("meeting_id", "")
    if chunk.chunk_type == "claim":
        url = f"/passport/{exp_id}" if exp_id else None
        title = meta.get("title") or f"主张 {chunk.ref_id}"
    elif chunk.chunk_type == "result":
        task_id = meta.get("task_id") or _lookup_task_id(db, chunk.ref_id)
        url = f"/result/{task_id}" if task_id else "/result"
        title = f"结果 {chunk.ref_id}"
    elif chunk.chunk_type == "evidence":
        url = f"/review/{meeting_id}" if meeting_id else None
        title = f"证据 {meta.get('speaker', '')} {meta.get('start_offset_sec', '')}".strip()
    else:  # failure_boundary
        task_id = meta.get("task_id") or _lookup_task_id(db, chunk.ref_id)
        url = f"/result/{task_id}" if task_id else "/result"
        title = f"失败边界 {chunk.ref_id}"
    return {
        "ref": ref_label,
        "type": chunk.chunk_type,
        "ref_id": chunk.ref_id,
        "title": title,
        "knowledge_status": chunk.knowledge_status,
        "url": url,
        "metadata": meta,
    }


def ask(db: Session, user: User, question: str) -> dict:
    """主入口：执行 RAG 问答。返回 QAAnswerOut 兼容 dict。"""
    t0 = time.time()
    question = (question or "").strip()
    if not question:
        return _refuse(
            question,
            reason="empty_question",
            missing=["请输入有效问题"],
            retrieval_details={},
        )

    # 启动时若索引为空且 DB 有可索引数据，触发一次全量重建
    try:
        ensure_index_ready(db)
    except Exception:
        pass

    # 步骤 1：权限前置过滤
    exp_ids = _user_experiments(db, user)
    if not exp_ids:
        return _refuse(
            question,
            reason="no_permission",
            missing=["无可见实验，请联系 PI 加入项目"],
            retrieval_details={"permission_filtered_experiments": 0},
        )

    # 步骤 2：状态过滤
    candidate_ids, candidate_chunks = _candidate_chunk_ids(db, exp_ids)
    if not candidate_ids:
        return _refuse(
            question,
            reason="no_match_after_status_filter",
            missing=["当前可见实验暂无可检索的已发布知识"],
            retrieval_details={
                "permission_filtered_experiments": len(exp_ids),
                "status_filtered_chunks": 0,
            },
        )
    chunks_by_id = {c.chunk_id: c for c in candidate_chunks}

    # 步骤 3：BM25 召回
    bm25_hits: list[tuple[str, float]] = []
    try:
        bm25_hits = vec.fts_search(db, question, settings.RAG_RECALL_TOP, candidate_ids)
    except Exception:
        pass
    bm25_scores = {cid: score for cid, score in bm25_hits}

    # 步骤 4：向量召回
    vec_hits: list[tuple[str, float]] = []
    emb_service = get_embedding_service()
    query_vec, emb_mode = emb_service.embed_query(question)
    try:
        if vec.vec_available(db):
            vec_hits = vec.vec_search(db, query_vec, settings.RAG_RECALL_TOP, candidate_ids)
    except Exception:
        pass
    # 把 distance（越小越相似）转为相似度（越大越相似）
    vec_scores = {cid: 1.0 / (1.0 + dist) for cid, dist in vec_hits}

    # 步骤 5：关系扩展
    hit_ids = set(bm25_scores.keys()) | set(vec_scores.keys())
    hit_chunks = [chunks_by_id[cid] for cid in hit_ids if cid in chunks_by_id]
    extra_ids = _relation_expand(db, hit_chunks, chunks_by_id)
    # 合并候选集
    all_candidate_ids = set(hit_ids) | set(extra_ids)
    all_candidates = [chunks_by_id[cid] for cid in all_candidate_ids if cid in chunks_by_id]

    # 步骤 6：重排
    ranked = _rerank(all_candidates, bm25_scores, vec_scores)
    if not ranked:
        return _refuse(
            question,
            reason="no_match_after_status_filter",
            missing=["检索未命中任何可信证据，请补充实验编号/参数名/适用范围后重试"],
            retrieval_details={
                "permission_filtered_experiments": len(exp_ids),
                "status_filtered_chunks": len(candidate_ids),
                "bm25_hits": len(bm25_hits),
                "vector_hits": len(vec_hits),
                "after_relation_expansion": len(all_candidate_ids),
                "after_rerank": 0,
                "top_score": 0.0,
            },
        )

    top_score = ranked[0][1]
    if top_score < settings.RAG_MIN_SCORE:
        return _refuse(
            question,
            reason="score_below_threshold",
            missing=[
                f"最高相似度 {top_score:.2f} 低于阈值 {settings.RAG_MIN_SCORE}",
                "请补充更具体的实验编号、参数名或适用范围",
            ],
            retrieval_details={
                "permission_filtered_experiments": len(exp_ids),
                "status_filtered_chunks": len(candidate_ids),
                "bm25_hits": len(bm25_hits),
                "vector_hits": len(vec_hits),
                "after_relation_expansion": len(all_candidate_ids),
                "after_rerank": len(ranked),
                "top_score": round(top_score, 4),
            },
        )

    # 步骤 7：上下文组装
    top_chunks = [c for c, _, _ in ranked]
    context_chunks = []
    for i, c in enumerate(top_chunks, 1):
        ref_label = f"C{i}"
        context_chunks.append(
            {
                "ref": ref_label,
                "type": c.chunk_type,
                "text": c.content_text,
                "metadata": c.metadata_json or {},
            }
        )

    # 步骤 8：LLM 生成
    llm = get_llm_service()
    answer_text, chat_mode = llm.chat(question, context_chunks)

    # 步骤 9：引用后处理
    is_refused, refusal_reason = detect_refusal(answer_text)
    if is_refused:
        return _refuse(
            question,
            reason="llm_refused",
            missing=[refusal_reason or "大模型判定证据不足"],
            retrieval_details={
                "permission_filtered_experiments": len(exp_ids),
                "status_filtered_chunks": len(candidate_ids),
                "bm25_hits": len(bm25_hits),
                "vector_hits": len(vec_hits),
                "after_relation_expansion": len(all_candidate_ids),
                "after_rerank": len(ranked),
                "top_score": round(top_score, 4),
            },
            model_info={
                "embedding_mode": emb_mode,
                "embedding_model": settings.QWEN_EMBEDDING_MODEL if emb_mode != "hash-fallback" else "hash-fallback",
                "chat_mode": chat_mode,
                "chat_model": llm.model_name,
                "top_k": settings.RAG_TOP_K,
            },
            citations=[_build_citation(c, f"C{i}", db) for i, (c, _, _) in enumerate(ranked, 1)],
        )

    # 提取 LLM 输出中的 [C1] [C2] 引用编号
    cited_refs = extract_citation_refs(answer_text)
    ref_to_chunk = {f"C{i}": c for i, (c, _, _) in enumerate(ranked, 1)}
    citations = []
    for ref in cited_refs:
        c = ref_to_chunk.get(ref)
        if c:
            citations.append(_build_citation(c, ref, db))

    # 待验证提示
    warning = None
    if top_chunks and top_chunks[0].chunk_type == "claim" and top_chunks[0].knowledge_status is None:
        warning = "unvalidated_claim"
        answer_text = f"⚠️ 该结论尚未经实验结果验证，仅作参考。\n\n{answer_text}"

    elapsed = round(time.time() - t0, 3)

    return {
        "question": question,
        "answer": answer_text,
        "citations": citations,
        "retrieval_scope": {
            "identity": user.display_name,
            "searched_experiments": len(exp_ids),
            "status_filter": ["current", "published"],
            "matched_claims": sum(1 for c in top_chunks if c.chunk_type == "claim"),
            "top_score": round(top_score, 4),
            "warning": warning,
        },
        "retrieval_details": {
            "permission_filtered_experiments": len(exp_ids),
            "status_filtered_chunks": len(candidate_ids),
            "bm25_hits": len(bm25_hits),
            "vector_hits": len(vec_hits),
            "after_relation_expansion": len(all_candidate_ids),
            "after_rerank": len(ranked),
            "top_score": round(top_score, 4),
            "score_breakdown": ranked[0][2] if ranked else {},
            "elapsed_sec": elapsed,
        },
        "model_info": {
            "embedding_mode": emb_mode,
            "embedding_model": settings.QWEN_EMBEDDING_MODEL if emb_mode != "hash-fallback" else "hash-fallback",
            "chat_mode": chat_mode,
            "chat_model": llm.model_name,
            "top_k": settings.RAG_TOP_K,
        },
        "missing_conditions": [],
        "refused": False,
    }


def _refuse(
    question: str,
    reason: str,
    missing: list[str],
    retrieval_details: dict,
    model_info: dict | None = None,
    citations: list | None = None,
) -> dict:
    return {
        "question": question,
        "answer": _REFUSE_TEXT.get(reason, "暂无满足证据和权限要求的可靠结论。"),
        "citations": citations or [],
        "retrieval_scope": {"reason": reason},
        "retrieval_details": retrieval_details,
        "model_info": model_info or {
            "embedding_mode": "hash-fallback",
            "embedding_model": "hash-fallback",
            "chat_mode": "template-fallback",
            "chat_model": "template",
            "top_k": settings.RAG_TOP_K,
        },
        "missing_conditions": missing,
        "refused": True,
    }


_REFUSE_TEXT = {
    "empty_question": "问题为空，请输入有效问题。",
    "no_permission": "暂无可检索的实验。请联系 PI 加入项目后再试。",
    "no_match_after_status_filter": "暂无满足证据和权限要求的可靠结论。请补充实验编号、参数名称或适用范围后重试。",
    "score_below_threshold": "检索到的证据与问题相关度不足。请补充更具体的实验编号、参数名或适用范围后重试。",
    "llm_refused": "基于当前证据无法给出可靠回答，请补充更多信息后重试。",
}
