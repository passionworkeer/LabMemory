"""10 个 MCP 工具实现。

每个工具复用 `app.api.aily` 的 10 个入站 endpoint 业务逻辑；
返回值精简版（≤2 万字）以遵守 Aily「返回数据 2 万字以内」建议，
全文细节通过 `jump_url` 暴露到平台前端。

关键设计：
- 直接调用 aily endpoint 函数（FastAPI Depends 在直接调用时不会触发）
- 返回值经 `_compact()` 精简：去掉 transcript 全文等大字段，仅保留 ID + 摘要 + jump_url
- 业务异常（NotFoundError / StateTransitionError）转 `CallToolResult(isError=True)`，
  由 Aily 模型根据错误信息决定下一步
- 装饰器 `@mcp_server.list_tools()` / `@mcp_server.call_tool()` 在模块导入时
  自动注册到 `app.mcp_server.mcp_server`，由 MCP Server 在协议层分发
"""
from __future__ import annotations

import asyncio
import json
import logging
from functools import lru_cache

import mcp.types as types
from sqlalchemy.orm import Session

from app.api import aily as aily_api
from app.config import settings
from app.core.errors import DomainError, NotFoundError, StateTransitionError
from app.db.locking import lock_experiment_for_write
from app.db.models import IntegrationRef, Meeting
from app.db.session import SessionLocal
from app.mcp_server import mcp_server
from app.services.aily_helpers import jump_url

logger = logging.getLogger(__name__)


def _resolve_meeting(db: Session, ref_type: str, ref_id: str) -> Meeting | None:
    """通过 IntegrationRef 解析到 Meeting（不抛异常，供加锁前定位 experiment_id）。"""
    if not ref_id:
        return None
    ref = db.query(IntegrationRef).filter(
        IntegrationRef.ref_type == ref_type,
        IntegrationRef.platform_id == ref_id,
    ).first()
    if ref is None:
        return None
    # ref.platform_type 可能是 "meeting" 或 "review"
    if ref.platform_type == "meeting":
        return db.query(Meeting).filter(Meeting.meeting_id == ref.platform_id).first()
    if ref.platform_type == "review":
        meeting_id = ref.platform_id
        return db.query(Meeting).filter(Meeting.meeting_id == meeting_id).first()
    return None


# === 工具清单（list_tools 返回） ===

TOOL_NAMES = (
    "labmemory_submit_transcript",
    "labmemory_submit_extraction",
    "labmemory_create_review",
    "labmemory_submit_verdict",
    "labmemory_issue_version",
    "labmemory_preflight_check",
    "labmemory_submit_execution",
    "labmemory_update_passport",
    "labmemory_publish_knowledge",
    "labmemory_create_reverify",
)


@lru_cache(maxsize=1)
def _tools_schema() -> list[types.Tool]:
    """10 个 MCP 工具的 schema 声明（与 aily.py 入参对齐）。

    M7 修复：lru_cache 后每次 list_tools 调用复用同一份 Tool 列表；
    返回的 list 浅拷给 SDK，避免 MCP 框架误改共享对象。
    """
    return [
        types.Tool(
            name="labmemory_submit_transcript",
            description=(
                "收妙记/逐字稿：把飞书会议 transcript 写入平台。"
                "调用前必须已知 meeting_id 与 experiment_id。"
            ),
            inputSchema={
                "type": "object",
                "required": ["meeting_id"],
                "properties": {
                    "meeting_id": {"type": "string", "description": "会议唯一 ID"},
                    "experiment_id": {"type": "string", "description": "实验编号（缺失回退 EXP-DEMO-001）"},
                    "note_id": {"type": "string"},
                    "speakers": {"type": "array", "items": {"type": "string"}},
                    "segments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start": {"type": "number"},
                                "end": {"type": "number"},
                                "speaker": {"type": "string"},
                                "text": {"type": "string"},
                            },
                        },
                    },
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="labmemory_submit_extraction",
            description="Aily 抽取结果回写：参数/争议/风险/任务候选。",
            inputSchema={
                "type": "object",
                "required": ["transcript_id"],
                "properties": {
                    "transcript_id": {"type": "string"},
                    "extraction_id": {"type": "string"},
                    "params": {"type": "array", "items": {"type": "object"}},
                    "disputes": {"type": "array", "items": {"type": "object"}},
                    "risks": {"type": "array", "items": {"type": "object"}},
                    "task_candidates": {"type": "array", "items": {"type": "object"}},
                    "scope": {"type": "object"},
                    "evidence": {"type": "array", "items": {"type": "object"}},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        ),
        types.Tool(
            name="labmemory_create_review",
            description="为抽取结果创建人工复核项；触发 decision.pending webhook。",
            inputSchema={
                "type": "object",
                "required": ["extraction_id"],
                "properties": {
                    "extraction_id": {"type": "string"},
                    "decision_id": {"type": "string"},
                    "assignee": {"type": "string", "description": "用户名（pi/lead/executor/admin）"},
                    "jump_url": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="labmemory_submit_verdict",
            description="人在平台点通过/驳回：verdict=pass 走六道闸门，reject 直接结束。",
            inputSchema={
                "type": "object",
                "required": ["decision_id", "verdict"],
                "properties": {
                    "decision_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["pass", "reject"]},
                    "reviewer": {"type": "string"},
                    "comment": {"type": "string"},
                    "verdict_at": {"type": "string", "description": "ISO 8601"},
                },
            },
        ),
        types.Tool(
            name="labmemory_issue_version",
            # H1 修复：文档化幂等语义——返回该决策项对应的最新 version_id；
            # 已有 claim 时不再构建新 claim，payload 中的 params 仅在首次生效。
            description=(
                "签发正式参数版本（幂等：已存在则返回该决策项当前最新 version_id，"
                "payload.params 仅在无现有 claim 时生效）。"
            ),
            inputSchema={
                "type": "object",
                "required": ["decision_id"],
                "properties": {
                    "decision_id": {"type": "string"},
                    "params": {"type": "array", "items": {"type": "object"}},
                    "effective_from": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
            },
        ),
        types.Tool(
            name="labmemory_preflight_check",
            description="执行前自检：版本/审批/资源/失败边界，不通过时触发 preflight.blocked webhook。",
            inputSchema={
                "type": "object",
                "required": ["version_id"],
                "properties": {
                    "version_id": {"type": "string"},
                    "executor": {"type": "string"},
                    "planned_at": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="labmemory_submit_execution",
            description="实际执行结果回写；actual_params 偏差时记 frozen 并触发 execution.deviated webhook。",
            inputSchema={
                "type": "object",
                "required": ["version_id", "actual_params", "results"],
                "properties": {
                    "version_id": {"type": "string"},
                    "actual_params": {"type": "object"},
                    "results": {"type": "object"},
                    "executor": {"type": "string"},
                    "executed_at": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="labmemory_update_passport",
            description="更新实验护照/主张状态/失败边界。",
            inputSchema={
                "type": "object",
                "properties": {
                    "passport_id": {"type": "string"},
                    "status": {"type": "string"},
                    "failure_boundary": {"type": "object"},
                    "claim_state": {"type": "string", "enum": ["supported", "partial_support", "refuted", "replaced", "insufficient"]},
                },
            },
        ),
        types.Tool(
            name="labmemory_publish_knowledge",
            description="发布知识（按护照下最新已提交结果）；触发 knowledge.ready webhook。",
            inputSchema={
                "type": "object",
                "required": ["passport_id"],
                "properties": {
                    "passport_id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "doc_refs": {"type": "array", "items": {"type": "string"}},
                    "claim_state": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="labmemory_create_reverify",
            description="创建复验任务；触发 reverify.due webhook（需后续调度器到点 fire）。",
            inputSchema={
                "type": "object",
                "required": ["passport_id"],
                "properties": {
                    "passport_id": {"type": "string"},
                    "assignee": {"type": "string"},
                    "due_at": {"type": "string"},
                    "criteria": {"type": "array", "items": {"type": "string"}},
                },
            },
        ),
    ]


# === 精简返回（≤2 万字） ===

def _compact(data: dict, *, keep_fields: list[str], default_jump_url: str | None = None) -> dict:
    """从 endpoint 返回值中保留指定字段；缺 jump_url 时补默认路由。"""
    out = {k: v for k, v in data.items() if k in keep_fields}
    if "jump_url" not in out and default_jump_url:
        out["jump_url"] = default_jump_url
    return out


# === 业务分发：HTTP endpoint 复用 ===

def _safe_close(db: Session) -> None:
    """M2 修复：异常路径（含 asyncio.CancelledError）显式 rollback 再 close。

    MCP SDK 在客户端断开时通过 anyio task group 取消 handler 任务，
    CancelledError 在 asyncio 层抛出。SQLAlchemy Session 在 uncommitted
    状态下 close 通常没问题，但 SQLite 单连接池下事务残留可能污染下次请求。
    """
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        pass
    try:
        db.close()
    except Exception:  # noqa: BLE001
        pass


def _invoke(name: str, arguments: dict) -> dict:
    """分发到具体工具实现；返回 dict（含 jump_url）；异常由上层包装为 CallToolResult。

    M2 修复：try/except 覆盖 CancelledError，finally 显式 rollback + close。
    """
    db: Session = SessionLocal()
    try:
        try:
            return _dispatch(name, arguments, db)
        except asyncio.CancelledError:
            # M2：客户端断开（anyio task group 取消 handler 任务），
            # 显式 rollback 让 SQLite 单连接池不被污染
            _safe_close(db)
            raise
    except asyncio.CancelledError:
        raise
    finally:
        _safe_close(db)


def _dispatch(name: str, arguments: dict, db: Session) -> dict:
    """实际分发逻辑（M2 拆分：与事务管理解耦）。"""
    if name == "labmemory_submit_transcript":
        payload = {**arguments}
        # L1 修复：MCP schema 不声明 metadata 字段，删除 metadata.experiment_id fallback
        payload.setdefault("experiment_id", settings.AILY_DEFAULT_EXPERIMENT_ID)
        result = aily_api.receive_transcript(payload, db)
        return _compact(
            result,
            keep_fields=["transcript_id", "meeting_id", "created"],
            default_jump_url=jump_url(f"/review/{result.get('meeting_id') or ''}"),
        )

    if name == "labmemory_submit_extraction":
        result = aily_api.receive_extraction(arguments, db)
        meeting_id = result.get("meeting_id") or arguments.get("transcript_id")
        return _compact(
            result,
            keep_fields=["extraction_id", "created", "candidate_ids"],
            default_jump_url=jump_url(f"/review/{meeting_id or ''}"),
        )

    if name == "labmemory_create_review":
        result = aily_api.create_decision(arguments, db)
        return _compact(result, keep_fields=["decision_id", "meeting_id", "jump_url"])

    if name == "labmemory_submit_verdict":
        decision_id = arguments["decision_id"]
        # C2 修复：写临界区加锁——保证同实验同 scope 同参数仅一个 current 主张
        meeting = _resolve_meeting(db, "decision", decision_id)
        if meeting is not None:
            with lock_experiment_for_write(db, meeting.experiment_id):
                result = aily_api.decision_verdict(decision_id, arguments, db)
        else:
            result = aily_api.decision_verdict(decision_id, arguments, db)
        compact = _compact(
            result,
            keep_fields=[
                "ack", "decision_id", "verdict", "version_id",
                "task_id", "publish_status", "gate_report",
            ],
            default_jump_url=jump_url("/review/"),
        )
        # M3 修复：gate_report 保留末尾 5 条（最 actionable 的失败描述往往在末端），
        # 同时输出总数让客户端知道截断量
        gr = compact.get("gate_report") or []
        if isinstance(gr, list) and len(gr) > 5:
            compact["gate_report_summary"] = {
                "shown": gr[-5:],
                "total": len(gr),
                "truncated": True,
            }
            compact.pop("gate_report", None)
        return compact

    if name == "labmemory_issue_version":
        decision_id = arguments.get("decision_id")
        # C2 修复：同 verdict — 写临界区加锁
        meeting = _resolve_meeting(db, "decision", decision_id or "")
        if meeting is not None:
            with lock_experiment_for_write(db, meeting.experiment_id):
                result = aily_api.issue_parameter_version(arguments, db)
        else:
            result = aily_api.issue_parameter_version(arguments, db)
        return _compact(
            result,
            keep_fields=["version_id", "created", "publish_status"],
            default_jump_url=jump_url("/review/"),
        )

    if name == "labmemory_preflight_check":
        result = aily_api.preflight(arguments, db)
        compact = _compact(
            result,
            keep_fields=["verdict", "reasons", "task_id"],
            default_jump_url=jump_url(f"/audit/{result.get('task_id') or ''}"),
        )
        reasons = compact.get("reasons") or []
        if isinstance(reasons, list) and len(reasons) > 5:
            # M3 修复：保留末尾 5 条（混合阻塞/确认原因，最 actionable 多在末端）
            compact["reasons_summary"] = {
                "shown": reasons[-5:],
                "total": len(reasons),
                "truncated": True,
            }
            compact.pop("reasons", None)
        # boundary_check 全文省略，仅保留 verdict/汇总
        compact.pop("boundary_check", None)
        return compact

    if name == "labmemory_submit_execution":
        result = aily_api.execution(arguments, db)
        return _compact(
            result,
            keep_fields=["execution_id", "status", "created"],
            default_jump_url=jump_url(f"/result/{result.get('execution_id') or ''}"),
        )

    if name == "labmemory_update_passport":
        passport_id = arguments.get("passport_id") or arguments.get("experiment_id")
        result = aily_api.update_passport(passport_id, arguments, db)
        return _compact(
            result,
            keep_fields=["passport_id", "experiment_id", "updated"],
            default_jump_url=jump_url(f"/passport/{passport_id or ''}"),
        )

    if name == "labmemory_publish_knowledge":
        result = aily_api.knowledge(arguments, db)
        return _compact(
            result,
            keep_fields=["knowledge_id", "title", "status", "idempotent"],
            default_jump_url=jump_url("/result/"),
        )

    if name == "labmemory_create_reverify":
        result = aily_api.reverify_task(arguments, db)
        return _compact(
            result,
            keep_fields=["reverify_id", "task_id"],
            default_jump_url=jump_url(f"/audit/{result.get('task_id') or ''}"),
        )

    raise NotFoundError(f"未知 MCP 工具：{name}")


def to_call_result(name: str, arguments: dict) -> types.CallToolResult:
    """统一异常处理：DomainError → isError=True，错误信息放 TextContent。"""
    try:
        data = _invoke(name, arguments)
        text = json.dumps(data, ensure_ascii=False, default=str)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            isError=False,
        )
    except (NotFoundError, StateTransitionError) as e:
        logger.warning(
            "MCP 工具业务异常：tool=%s code=%s msg=%s",
            name, getattr(e, "code", "?"), e.message,
        )
        err = {
            "tool": name,
            "code": getattr(e, "code", "not_found" if isinstance(e, NotFoundError) else "state_transition"),
            "message": e.message,
            "details": getattr(e, "details", {}),
        }
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(err, ensure_ascii=False))],
            isError=True,
        )
    except DomainError as e:
        err = {"tool": name, "code": e.code, "message": e.message, "details": e.details}
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(err, ensure_ascii=False))],
            isError=True,
        )
    except Exception as e:  # noqa: BLE001
        # C3 修复：catch-all 不向客户端泄漏内部细节（SQL/堆栈/文件路径）
        # 详细错误只进服务端日志；客户端收到通用消息 + 关联 ID 便于排查
        import uuid

        cid = uuid.uuid4().hex[:12]
        logger.exception("MCP 工具未预期异常：tool=%s cid=%s", name, cid)
        err = {
            "tool": name,
            "code": "internal_error",
            "message": "内部错误，请联系运维（提供 cid 以便排查）",
            "correlation_id": cid,
        }
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(err, ensure_ascii=False))],
            isError=True,
        )


# === 注册 handlers 到 mcp_server（模块导入时即生效） ===

@mcp_server.list_tools()
async def _list_tools() -> list[types.Tool]:
    """Aily 客户端 initialize 后会调用 list_tools 拉清单。"""
    return _tools_schema()


@mcp_server.call_tool()
async def _call_tool(name: str, arguments: dict) -> types.CallToolResult:
    """所有 10 个工具的统一入口；委托 to_call_result。

    返回 CallToolResult 让 SDK 直接透传（保留 isError 标志）；
    若返回 list[TextContent]，SDK 会强制 isError=False，业务异常会被吃掉。
    """
    return to_call_result(name, arguments)


__all__ = ["_tools_schema", "_invoke", "to_call_result", "TOOL_NAMES"]