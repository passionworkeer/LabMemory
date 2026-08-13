"""sqlite-vec 适配层。

负责：
- 在指定 SQLAlchemy 连接上加载 sqlite-vec 扩展
- 创建/确保 vec_chunks 虚拟表存在
- 提供 upsert / search / delete 工具

设计要点：
- sqlite-vec 通过 sqlite3 load_extension 加载；SQLAlchemy 的 raw_connection 暴露 sqlite3 连接
- 向量以 BLOB（float32 little-endian）存储
- chunk_id 作为外键关联 embedding_chunks.rowid
"""
from __future__ import annotations

import struct
from typing import Iterable, Sequence

import sqlite_vec
from sqlalchemy.orm import Session


def _raw_conn(db_session: Session):
    """获取底层 sqlite3 连接，并加载 sqlite-vec 扩展。"""
    conn = db_session.connection().connection
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception:
        # 已加载或扩展不可用，忽略
        pass
    return conn


def ensure_vec_tables(db_session: Session, dim: int) -> bool:
    """创建 vec_chunks 虚拟表与 chunks_fts 倒排表。返回 vec_chunks 是否建表成功。

    FTS5（chunks_fts）是 SQLite 内置，恒可建；vec0（vec_chunks）依赖 sqlite-vec 扩展，
    可能加载失败。两者独立处理：vec 不可用时 FTS 仍可用，QA 可降级为 BM25（decision-qa）。
    """
    conn = _raw_conn(db_session)
    cur = conn.cursor()
    # FTS5 内置：先确保倒排表，BM25 召回依赖它
    try:
        cur.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
            "chunk_id UNINDEXED, content_text, tokenize='unicode61'"
            ")"
        )
        conn.commit()
    except Exception:
        pass
    # vec0 依赖 sqlite-vec 扩展：单独 try，失败不影响 FTS
    try:
        cur.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{dim}], chunk_id text)"
        )
        conn.commit()
        return True
    except Exception:
        return False


def vec_available(db_session: Session) -> bool:
    """检查 sqlite-vec 是否可用（扩展可加载且虚拟表存在）。"""
    try:
        conn = _raw_conn(db_session)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vec_chunks'")
        return cur.fetchone() is not None
    except Exception:
        return False


def _encode_vec(vec: Sequence[float]) -> bytes:
    """把 float 序列编码为 sqlite-vec 期望的 BLOB（float32 little-endian）。"""
    try:
        return sqlite_vec.serialize_float32(list(vec))
    except Exception:
        # 回退到手工编码（float32 little-endian）
        return struct.pack(f"<{len(vec)}f", *vec)


def vec_upsert(db_session: Session, chunk_id: str, embedding: Sequence[float]) -> None:
    """插入或替换一条向量（以 chunk_id 为主键去重）。"""
    conn = _raw_conn(db_session)
    cur = conn.cursor()
    blob = _encode_vec(embedding)
    cur.execute("DELETE FROM vec_chunks WHERE chunk_id = ?", (chunk_id,))
    cur.execute(
        "INSERT INTO vec_chunks(chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, blob),
    )
    conn.commit()


def vec_delete(db_session: Session, chunk_ids: Iterable[str]) -> None:
    ids = list(chunk_ids)
    if not ids:
        return
    conn = _raw_conn(db_session)
    cur = conn.cursor()
    placeholders = ",".join("?" * len(ids))
    cur.execute(f"DELETE FROM vec_chunks WHERE chunk_id IN ({placeholders})", ids)
    conn.commit()


def vec_search(
    db_session: Session,
    query_embedding: Sequence[float],
    k: int,
    candidate_chunk_ids: list[str] | None = None,
) -> list[tuple[str, float]]:
    """KNN 检索。返回 [(chunk_id, distance), ...]（distance 越小越相似）。

    candidate_chunk_ids 非空时在 SQL 层做权限/状态前置过滤，避免全库扫描后过滤。
    """
    if not candidate_chunk_ids:
        return []
    conn = _raw_conn(db_session)
    cur = conn.cursor()
    blob = _encode_vec(query_embedding)
    placeholders = ",".join("?" * len(candidate_chunk_ids))
    sql = (
        f"SELECT chunk_id, distance FROM vec_chunks "
        f"WHERE chunk_id IN ({placeholders}) AND embedding MATCH ? AND k = ? "
        f"ORDER BY distance"
    )
    rows = cur.execute(sql, [*candidate_chunk_ids, blob, k]).fetchall()
    return [(r[0], float(r[1])) for r in rows]


def fts_upsert(db_session: Session, chunk_id: str, content_text: str) -> None:
    """插入或替换 FTS5 索引项。"""
    conn = _raw_conn(db_session)
    cur = conn.cursor()
    cur.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
    cur.execute(
        "INSERT INTO chunks_fts(chunk_id, content_text) VALUES (?, ?)",
        (chunk_id, content_text),
    )
    conn.commit()


def fts_delete(db_session: Session, chunk_ids: Iterable[str]) -> None:
    ids = list(chunk_ids)
    if not ids:
        return
    conn = _raw_conn(db_session)
    cur = conn.cursor()
    placeholders = ",".join("?" * len(ids))
    cur.execute(f"DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})", ids)
    conn.commit()


def fts_search(
    db_session: Session,
    query: str,
    k: int,
    candidate_chunk_ids: list[str] | None = None,
) -> list[tuple[str, float]]:
    """BM25 检索。返回 [(chunk_id, score), ...]，score 为 bm25 值（越小越相关，取负转相似度）。"""
    if not candidate_chunk_ids or not query.strip():
        return []
    conn = _raw_conn(db_session)
    cur = conn.cursor()
    # FTS5 MATCH 需对查询做基本转义（FTS5 语法对 - " 等敏感）
    safe_query = " ".join(tok for tok in query.replace('"', " ").split() if tok)
    if not safe_query:
        return []
    placeholders = ",".join("?" * len(candidate_chunk_ids))
    sql = (
        f"SELECT chunk_id, bm25(chunks_fts) AS score FROM chunks_fts "
        f"WHERE chunks_fts MATCH ? AND chunk_id IN ({placeholders}) "
        f"ORDER BY score LIMIT ?"
    )
    rows = cur.execute(sql, [safe_query, *candidate_chunk_ids, k]).fetchall()
    # bm25 返回负值（越小越相关），转为正相似度：score = -bm25
    return [(r[0], -float(r[1])) for r in rows]
