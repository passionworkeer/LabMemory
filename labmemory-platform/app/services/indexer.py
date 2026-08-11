"""RAG 索引器：把 Claim/Result/Evidence/FailureBoundary 切片写入向量库与 FTS 索引。

切片粒度：
- claim: 1 主张 1 片（status=current）
- result: 1 结果 1 片（status=published）
- evidence: 1 会议逐字稿段 1 片（会议已复核确认）
- failure_boundary: 1 结果 1 片（含 failure_boundary 的 published 结果）
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from sqlalchemy.orm import Session

from app.config import settings
from app.db import vec
from app.db.models import Claim, EmbeddingChunk, Experiment, Meeting, MeetingReview, Result
from app.services.embedding import get_embedding_service


# === 文本组装 ===

def _claim_text(claim: Claim, exp: Experiment) -> str:
    content = claim.content or {}
    pv = claim.parameter_version or {}
    parts = [
        f"[claim {claim.claim_id} v{pv.get('version', '?')} {claim.status}]",
        content.get("title", ""),
    ]
    if content.get("description"):
        parts.append(content["description"])
    # 三元组
    subj = content.get("subject")
    pred = content.get("predicate")
    obj = content.get("object")
    if subj and pred and obj:
        parts.append(f"{subj} {pred} {obj}")
    # 条件
    cond = content.get("conditions")
    if cond:
        cond_str = ", ".join(f"{k}={v}" for k, v in cond.items())
        parts.append(f"条件: {cond_str}")
    # 参数版本
    if pv:
        params = pv.get("parameters", [])
        if params:
            p_str = ", ".join(
                f"{p.get('name','')}={p.get('value','')}{p.get('unit','')}"
                for p in params
            )
            parts.append(f"参数版本 {pv.get('version', '?')}: {p_str}")
        scope = pv.get("scope")
        if scope:
            scope_str = ", ".join(f"{k}={v}" for k, v in scope.items())
            parts.append(f"适用范围: {scope_str}")
    # 知识状态
    if claim.knowledge_status:
        parts.append(f"知识状态: {claim.knowledge_status}")
    # 证据摘要
    evidence = content.get("evidence", [])
    if evidence:
        for ev in evidence[:3]:
            speaker = ev.get("speaker", "")
            text = ev.get("text", "")
            parts.append(f"证据-{speaker}: {text}")
    return " ".join(p for p in parts if p)


def _result_text(result: Result, exp: Experiment) -> str:
    parts = [
        f"[result {result.result_id} {result.status}]",
        f"实验 {exp.experiment_id}",
    ]
    if result.actual_params:
        params = result.actual_params if isinstance(result.actual_params, list) else [result.actual_params]
        for p in params:
            if isinstance(p, dict):
                parts.append(f"实际参数 {p.get('name','')}={p.get('value','')}{p.get('unit','')}")
    if result.metrics:
        m_str = ", ".join(f"{k}={v}" for k, v in result.metrics.items())
        parts.append(f"指标: {m_str}")
    if result.knowledge_status:
        parts.append(f"知识状态: {result.knowledge_status}")
    if result.notes:
        parts.append(f"备注: {result.notes}")
    return " ".join(p for p in parts if p)


def _evidence_text(meeting: Meeting, seg: dict, idx: int) -> str:
    speaker = seg.get("speaker", "")
    text = seg.get("text", "")
    start = seg.get("start_offset_sec", "")
    return (
        f"[evidence {meeting.meeting_id}#{idx}] "
        f"会议 {meeting.title} - {speaker} {start}: {text}"
    )


def _boundary_text(result: Result, exp: Experiment) -> str:
    fb = result.failure_boundary or {}
    parts = [
        f"[failure_boundary {result.result_id}]",
        f"实验 {exp.experiment_id}",
    ]
    if fb.get("phenomenon"):
        parts.append(f"现象: {fb['phenomenon']}")
    if fb.get("trigger_condition"):
        parts.append(f"触发条件: {fb['trigger_condition']}")
    if fb.get("root_cause_status"):
        parts.append(f"根因状态: {fb['root_cause_status']}")
    if fb.get("next_step"):
        parts.append(f"后续动作: {fb['next_step']}")
    return " ".join(p for p in parts if p)


# === 元数据组装 ===

def _claim_meta(claim: Claim, exp: Experiment) -> dict:
    pv = claim.parameter_version or {}
    content = claim.content or {}
    return {
        "claim_id": claim.claim_id,
        "experiment_id": exp.experiment_id,
        "version": pv.get("version"),
        "title": content.get("title", ""),
        "knowledge_status": claim.knowledge_status,
        "parameter_version": pv,
        "captured_at": (claim.created_at.isoformat() if claim.created_at else None),
    }


def _result_meta(result: Result, exp: Experiment, task=None) -> dict:
    return {
        "result_id": result.result_id,
        "experiment_id": exp.experiment_id,
        "task_id": task.task_id if task else None,
        "metrics": result.metrics,
        "knowledge_status": result.knowledge_status,
        "published_at": (result.published_at.isoformat() if result.published_at else None),
    }


def _evidence_meta(meeting: Meeting, seg: dict, idx: int) -> dict:
    return {
        "meeting_id": meeting.meeting_id,
        "experiment_id": None,  # 上层填充
        "segment_index": idx,
        "speaker": seg.get("speaker"),
        "start_offset_sec": seg.get("start_offset_sec"),
        "title": meeting.title,
    }


def _boundary_meta(result: Result, exp: Experiment, task=None) -> dict:
    return {
        "result_id": result.result_id,
        "experiment_id": exp.experiment_id,
        "task_id": task.task_id if task else None,
        "phenomenon": (result.failure_boundary or {}).get("phenomenon"),
        "root_cause_status": (result.failure_boundary or {}).get("root_cause_status"),
    }


# === 切片 upsert ===

def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _upsert_chunk(
    db: Session,
    chunk_id: str,
    chunk_type: str,
    ref_id: str,
    experiment_id: int,
    project_id: int,
    status: str,
    knowledge_status: str | None,
    content_text: str,
    metadata: dict,
) -> EmbeddingChunk:
    content_hash = _hash_text(content_text)
    existing = db.query(EmbeddingChunk).filter(EmbeddingChunk.chunk_id == chunk_id).first()
    emb_service = get_embedding_service()

    if existing and existing.content_hash == content_hash:
        # 内容未变：仅更新 status/knowledge_status（可能因主张被替代而变化）
        if existing.status != status or existing.knowledge_status != knowledge_status:
            existing.status = status
            existing.knowledge_status = knowledge_status
            db.flush()
        return existing

    # 新切片或内容变化：重新嵌入
    embeddings, emb_mode = emb_service.embed_texts([content_text])
    embedding = embeddings[0] if embeddings else [0.0] * emb_service.dim

    if existing:
        existing.chunk_type = chunk_type
        existing.ref_id = ref_id
        existing.experiment_id = experiment_id
        existing.project_id = project_id
        existing.status = status
        existing.knowledge_status = knowledge_status
        existing.content_text = content_text
        existing.content_hash = content_hash
        existing.metadata_json = metadata
        existing.embedding_model = emb_mode
        db.flush()
    else:
        existing = EmbeddingChunk(
            chunk_id=chunk_id,
            chunk_type=chunk_type,
            ref_id=ref_id,
            experiment_id=experiment_id,
            project_id=project_id,
            status=status,
            knowledge_status=knowledge_status,
            content_text=content_text,
            content_hash=content_hash,
            metadata_json=metadata,
            embedding_model=emb_mode,
        )
        db.add(existing)
        db.flush()

    # 同步向量库与 FTS 索引
    try:
        vec.vec_upsert(db, chunk_id, embedding)
        vec.fts_upsert(db, chunk_id, content_text)
    except Exception:
        # 向量库不可用时仅不索引，不阻塞业务
        pass

    return existing


# === 单条索引入口 ===

def index_claim(db: Session, claim: Claim) -> EmbeddingChunk | None:
    if claim.status != "current":
        # 旧版本主张：标记为 superseded，不重新嵌入
        return mark_claim_superseded(db, claim.claim_id)
    exp = db.get(Experiment, claim.experiment_id)
    if not exp:
        return None
    text = _claim_text(claim, exp)
    meta = _claim_meta(claim, exp)
    return _upsert_chunk(
        db,
        chunk_id=f"claim:{claim.claim_id}",
        chunk_type="claim",
        ref_id=claim.claim_id,
        experiment_id=claim.experiment_id,
        project_id=exp.project_id,
        status="current",
        knowledge_status=claim.knowledge_status,
        content_text=text,
        metadata=meta,
    )


def index_result(db: Session, result: Result) -> EmbeddingChunk | None:
    if result.status != "published":
        return None
    from app.db.models import Task
    task = db.get(Task, result.task_id)
    if not task:
        return None
    exp = db.get(Experiment, task.experiment_id)
    if not exp:
        return None
    text = _result_text(result, exp)
    meta = _result_meta(result, exp, task)
    return _upsert_chunk(
        db,
        chunk_id=f"result:{result.result_id}",
        chunk_type="result",
        ref_id=result.result_id,
        experiment_id=exp.id,
        project_id=exp.project_id,
        status="published",
        knowledge_status=result.knowledge_status,
        content_text=text,
        metadata=meta,
    )


def index_meeting(db: Session, meeting: Meeting) -> list[EmbeddingChunk]:
    """索引会议逐字稿各段为 evidence 切片。"""
    exp = db.get(Experiment, meeting.experiment_id)
    if not exp:
        return []
    transcript = meeting.transcript or []
    if not isinstance(transcript, list):
        return []
    chunks: list[EmbeddingChunk] = []
    for idx, seg in enumerate(transcript):
        if not isinstance(seg, dict) or not seg.get("text"):
            continue
        text = _evidence_text(meeting, seg, idx)
        meta = _evidence_meta(meeting, seg, idx)
        meta["experiment_id"] = exp.experiment_id
        meta["title"] = meeting.title
        c = _upsert_chunk(
            db,
            chunk_id=f"evidence:{meeting.meeting_id}#seg{idx}",
            chunk_type="evidence",
            ref_id=f"{meeting.meeting_id}#seg{idx}",
            experiment_id=meeting.experiment_id,
            project_id=exp.project_id,
            status="active",
            knowledge_status=None,
            content_text=text,
            metadata=meta,
        )
        chunks.append(c)
    return chunks


def index_failure_boundary(db: Session, result: Result) -> EmbeddingChunk | None:
    if result.status != "published" or not result.failure_boundary:
        return None
    from app.db.models import Task
    task = db.get(Task, result.task_id)
    if not task:
        return None
    exp = db.get(Experiment, task.experiment_id)
    if not exp:
        return None
    text = _boundary_text(result, exp)
    meta = _boundary_meta(result, exp, task)
    return _upsert_chunk(
        db,
        chunk_id=f"boundary:{result.result_id}",
        chunk_type="failure_boundary",
        ref_id=result.result_id,
        experiment_id=exp.id,
        project_id=exp.project_id,
        status="published",
        knowledge_status=None,
        content_text=text,
        metadata=meta,
    )


def mark_claim_superseded(db: Session, claim_id: str) -> None:
    chunk = db.query(EmbeddingChunk).filter(EmbeddingChunk.chunk_id == f"claim:{claim_id}").first()
    if chunk and chunk.status != "superseded":
        chunk.status = "superseded"
        db.flush()


# === 全量重建 ===

def reindex_all(db: Session) -> dict:
    """清空所有索引并重建。返回统计信息。"""
    # 清空三张表
    db.query(EmbeddingChunk).delete()
    try:
        conn = db.connection().connection
        conn.execute("DELETE FROM vec_chunks")
        conn.execute("DELETE FROM chunks_fts")
        conn.commit()
    except Exception:
        pass

    stats = {"claims": 0, "results": 0, "evidence": 0, "boundaries": 0, "errors": []}

    # Claim
    for claim in db.query(Claim).filter(Claim.status == "current").all():
        try:
            if index_claim(db, claim):
                stats["claims"] += 1
        except Exception as e:
            stats["errors"].append(f"claim:{claim.claim_id} - {e}")

    # Result + FailureBoundary
    for result in db.query(Result).filter(Result.status == "published").all():
        try:
            if index_result(db, result):
                stats["results"] += 1
            if index_failure_boundary(db, result):
                stats["boundaries"] += 1
        except Exception as e:
            stats["errors"].append(f"result:{result.result_id} - {e}")

    # Evidence（仅已复核确认的会议）
    confirmed_meetings = (
        db.query(Meeting)
        .join(MeetingReview, MeetingReview.meeting_id == Meeting.id)
        .filter(MeetingReview.status == "processed", MeetingReview.decision == "confirmed")
        .all()
    )
    for meeting in confirmed_meetings:
        try:
            chunks = index_meeting(db, meeting)
            stats["evidence"] += len(chunks)
        except Exception as e:
            stats["errors"].append(f"meeting:{meeting.meeting_id} - {e}")

    db.commit()
    return stats


def ensure_index_ready(db: Session) -> dict | None:
    """若索引为空且 DB 有可索引数据，触发一次全量重建。"""
    count = db.query(EmbeddingChunk).count()
    if count > 0:
        return None
    has_data = (
        db.query(Claim).filter(Claim.status == "current").count() > 0
        or db.query(Result).filter(Result.status == "published").count() > 0
    )
    if not has_data:
        return None
    return reindex_all(db)
