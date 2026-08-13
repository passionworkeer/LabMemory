"""按实验串行化写临界区的锁工具。

保护「同实验同 scope 同参数仅一个 current 主张」等可信不变量在并发下成立。
uvicorn 把同步路由派发到线程池（默认 40 线程），单进程内也存在并发；多进程
部署（生产建议 Postgres）下叠加行锁跨进程串行。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

_guard = threading.Lock()
_locks: dict[int, threading.Lock] = {}


def _lock_for(experiment_id: int) -> threading.Lock:
    with _guard:
        lk = _locks.get(experiment_id)
        if lk is None:
            lk = threading.Lock()
            _locks[experiment_id] = lk
        return lk


@contextmanager
def lock_experiment_for_write(db: Session, experiment_id: int) -> Iterator[None]:
    """串行化某实验的写临界区（读旧 current → supersede → 写新 current → commit）。

    - 进程内：按 experiment_id 的 threading.Lock。
    - Postgres：SELECT ... FOR UPDATE 锁实验行，跨进程串行。
    SQLite 多进程部署天然单写者，不在此覆盖（见 change design D1）。
    """
    try:
        dialect_name = db.bind.dialect.name if db.bind else ""
    except Exception:  # noqa: BLE001
        dialect_name = ""
    lk = _lock_for(experiment_id)
    lk.acquire()
    try:
        if dialect_name and dialect_name != "sqlite":
            from sqlalchemy import select

            from app.db.models import Experiment

            db.execute(
                select(Experiment)
                .where(Experiment.id == experiment_id)
                .with_for_update()
            )
        yield
    finally:
        lk.release()
