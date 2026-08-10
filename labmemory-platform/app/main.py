"""LabMemory 平台主应用入口。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import admin as admin_api
from app.api import auth as auth_api
from app.api import brief as brief_api
from app.api import control_tower as control_tower_api
from app.api import experiments as experiments_api
from app.api import meetings as meetings_api
from app.api import passport as passport_api
from app.api import qa as qa_api
from app.api import results as results_api
from app.api import tasks as tasks_api
from app.api.deps import get_db
from app.config import settings
from app.core.errors import DomainError
from app.db.base import Base
from app.db.session import engine

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LabMemory 平台启动 db=%s", settings.DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    yield
    logger.info("LabMemory 平台关闭")


def _run_migrations() -> None:
    """轻量迁移：为已有 tasks 表补充新列（SQLite ALTER TABLE ADD COLUMN）。"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "tasks" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("tasks")}
    new_cols = [
        ("approval_status", "VARCHAR(32) DEFAULT 'pending' NOT NULL"),
        ("approved_by", "INTEGER"),
        ("approved_at", "DATETIME"),
        ("approval_note", "TEXT"),
        ("resource_status", "VARCHAR(32) DEFAULT 'pending' NOT NULL"),
        ("resources", "JSON"),
        ("failure_boundary_ack", "BOOLEAN DEFAULT 0 NOT NULL"),
    ]
    with engine.begin() as conn:
        for col, ddl in new_cols:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col} {ddl}"))
                logger.info("迁移：tasks 表新增列 %s", col)

    # 去掉 uq_task_per_meeting 唯一约束（一键修正需为同一会议生成新任务草稿，旧任务保留为 blocked）
    with engine.connect() as conn:
        sql = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
        ).scalar()
        if sql and "uq_task_per_meeting" in sql:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.exec_driver_sql("""
                CREATE TABLE tasks_new (
                    task_id VARCHAR(64) NOT NULL,
                    meeting_id INTEGER NOT NULL,
                    experiment_id INTEGER NOT NULL,
                    claim_id INTEGER,
                    status VARCHAR(32) NOT NULL,
                    assignee_id INTEGER,
                    due_date DATETIME,
                    planned_params JSON,
                    id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    approval_status VARCHAR(32) DEFAULT 'pending' NOT NULL,
                    approved_by INTEGER,
                    approved_at DATETIME,
                    approval_note TEXT,
                    resource_status VARCHAR(32) DEFAULT 'pending' NOT NULL,
                    resources JSON,
                    failure_boundary_ack BOOLEAN DEFAULT 0 NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(meeting_id) REFERENCES meetings (id),
                    FOREIGN KEY(experiment_id) REFERENCES experiments (id),
                    FOREIGN KEY(claim_id) REFERENCES claims (id),
                    FOREIGN KEY(assignee_id) REFERENCES users (id),
                    FOREIGN KEY(approved_by) REFERENCES users (id)
                )
            """)
            conn.exec_driver_sql("INSERT INTO tasks_new SELECT * FROM tasks")
            conn.exec_driver_sql("DROP TABLE tasks")
            conn.exec_driver_sql("ALTER TABLE tasks_new RENAME TO tasks")
            conn.exec_driver_sql("CREATE UNIQUE INDEX ix_tasks_task_id ON tasks (task_id)")
            conn.exec_driver_sql("CREATE INDEX ix_tasks_id ON tasks (id)")
            conn.exec_driver_sql("CREATE INDEX ix_tasks_experiment_id ON tasks (experiment_id)")
            conn.exec_driver_sql("CREATE INDEX ix_tasks_meeting_id ON tasks (meeting_id)")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.commit()
            logger.info("迁移：tasks 表移除 uq_task_per_meeting 唯一约束（一键修正可生成同会议新任务）")


app = FastAPI(
    title="LabMemory 可信决策平台",
    description="实验决策与记忆系统 - 简化版（会后复核 / 行动审计 / 结果回流 / 实验护照）",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.utcnow()
    response = await call_next(request)
    duration_ms = (datetime.utcnow() - start).total_seconds() * 1000
    logger.info("%s %s - %d - %.2fms", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "details": exc.details},
    )


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "service": "labmemory-platform",
        "version": "2.0.0",
        "data_source": "sqlite",
        "timestamp": datetime.utcnow().isoformat(),
    }


# === 路由 ===
app.include_router(admin_api.router)
app.include_router(auth_api.router)
app.include_router(control_tower_api.router)
app.include_router(experiments_api.router)
app.include_router(brief_api.router)
app.include_router(meetings_api.router)
app.include_router(tasks_api.router)
app.include_router(results_api.router)
app.include_router(passport_api.router)
app.include_router(passport_api.list_router)
app.include_router(qa_api.router)


# === 前端静态文件 ===
# 优先 frontend/dist/（npm run build 产物）；回退 app/static/（仅登录占位）
_DIST_CANDIDATES = [
    settings.PROJECT_ROOT / "frontend" / "dist",
    settings.PROJECT_ROOT / "app" / "static",
]
_dist_dir = next((d for d in _DIST_CANDIDATES if (d / "index.html").exists()), None)

if _dist_dir is not None:
    assets_dir = _dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    logger.info("前端 dist 挂载 -> %s", _dist_dir)

    @app.get("/")
    def root_index():
        return FileResponse(str(_dist_dir / "index.html"))

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "v1/", "health", "docs", "redoc", "openapi", "assets/", "static/")):
            raise HTTPException(status_code=404, detail=f"Not found: /{full_path}")
        return FileResponse(str(_dist_dir / "index.html"))
else:
    logger.warning("前端 dist 不存在：请运行 `cd frontend && npm install && npm run build`")

    @app.get("/")
    def root_fallback():
        return {
            "message": "LabMemory 可信决策平台（前端未构建）",
            "docs": "/docs",
            "health": "/health",
            "hint": "cd frontend && npm install && npm run build",
        }
