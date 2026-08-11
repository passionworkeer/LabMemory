"""数据库会话管理（SQLAlchemy 2.0，SQLite/PostgreSQL 兼容）。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

_connect_args: dict = {}
_kwargs: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    # in-memory SQLite 默认每连接一个独立库；测试场景下需要共享同一库
    if settings.DATABASE_URL in ("sqlite://", "sqlite:///:memory:"):
        _kwargs["poolclass"] = StaticPool

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args=_connect_args,
    **_kwargs,
)


_VEC_LOADED_FLAG = "_labmemory_vec_loaded"


def _load_vec_extension(dbapi_conn) -> None:
    """在每个 SQLite 连接上加载 sqlite-vec 扩展（幂等）。"""
    if getattr(dbapi_conn, _VEC_LOADED_FLAG, False):
        return
    try:
        dbapi_conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)
    except Exception:
        # sqlite-vec 未安装或扩展加载被禁用；向量功能降级，但不阻断连接
        pass
    finally:
        try:
            setattr(dbapi_conn, _VEC_LOADED_FLAG, True)
        except Exception:
            pass


if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _on_sqlite_connect(dbapi_conn, connection_record):
        _load_vec_extension(dbapi_conn)


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
