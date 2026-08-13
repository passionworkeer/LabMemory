"""管理员接口：重置演示数据、模拟飞书推送等。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import new_id
from app.db.models import (
    ActionAudit,
    AuditEvent,
    Candidate,
    Claim,
    Experiment,
    Meeting,
    MeetingReview,
    Result,
    Task,
    User,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(user: User) -> User:
    if user.global_role != "admin":
        # 仅 admin 可清空全平台业务数据（PI 不应能清空他人项目）
        from app.core.errors import PermissionDeniedError
        raise PermissionDeniedError("仅管理员可重置演示数据")
    return user


@router.post("/reset-demo")
def reset_demo_data(
    mode: str = "api",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """重置演示数据。

    mode:
      - ``clear`` — 仅清除业务数据
      - ``pending`` — 清除后通过飞书接口逻辑模拟推送（所有会议待复核）
      - ``full`` — 清除后直接写库注入完整链路（含已完成/已阻断/已发布）
    """
    _require_admin(user)

    if mode not in ("clear", "pending", "full"):
        raise HTTPException(status_code=400, detail="mode 必须是 clear / pending / full")

    # 清除业务数据
    db.query(Result).delete()
    db.query(ActionAudit).delete()
    db.query(Task).delete()
    db.query(Claim).delete()
    db.query(Candidate).delete()
    db.query(MeetingReview).delete()
    db.query(Meeting).delete()
    db.query(AuditEvent).delete()
    db.flush()

    # 清空 RAG 索引（业务数据已清，索引也应清空）
    try:
        from app.db.models import EmbeddingChunk
        db.query(EmbeddingChunk).delete()
        conn = db.connection().connection
        conn.execute("DELETE FROM vec_chunks")
        conn.execute("DELETE FROM chunks_fts")
        conn.commit()
    except Exception:
        pass

    if mode == "clear":
        db.commit()
        return {"status": "ok", "mode": mode, "message": "已清除所有业务数据"}

    # 确保有实验
    exp = db.query(Experiment).filter(Experiment.experiment_id == "EXP-DEMO-001").first()
    if exp is None:
        raise HTTPException(
            status_code=404,
            detail="实验 EXP-DEMO-001 不存在，请先创建实验或运行 seed_demo",
        )

    if mode == "pending":
        _seed_pending_only(db, exp, user)
    else:
        _seed_full_chain(db, exp, user)

    db.commit()

    # 重置后全量重建 RAG 索引
    try:
        from app.services.indexer import reindex_all
        reindex_all(db)
        db.commit()
    except Exception:
        pass

    return {"status": "ok", "mode": mode, "message": f"演示数据已重置（{mode} 模式）"}


def _seed_pending_only(db: Session, exp: Experiment, actor: User) -> None:
    """模拟飞书推送：4 个待复核会议（无已处理数据）。

    这些会议后续需要用户在前端手动确认，才能推进链路。
    """
    now = datetime.now(timezone.utc)

    scenarios = [
        {
            "mid": "meet_demo_65c",
            "title": "Compound-A 60→65℃ 升温评审",
            "delta": timedelta(days=-2),
            "candidates": [
                {
                    "type": "parameter_change",
                    "title": "温度 60→65℃ 升温",
                    "description": "提升转化率",
                    "parameters": [
                        {"name": "temperature", "value": "65", "unit": "℃"},
                        {"name": "time", "value": "2", "unit": "h"},
                        {"name": "catalyst", "value": "1.0", "unit": "eq"},
                    ],
                    "confidence": 0.9,
                },
            ],
            "transcript": [
                {"speaker": "陈工", "start_offset_sec": 10, "end_offset_sec": 18,
                 "text": "上一轮 60℃ 转化率只有 63%，建议升到 65℃"},
                {"speaker": "赵负责人", "start_offset_sec": 20, "end_offset_sec": 30,
                 "text": "同意，验收看转化率≥75%且副产物≤6%"},
            ],
        },
        {
            "mid": "meet_demo_80c",
            "title": "Compound-A 80℃ 暂定参数评审",
            "delta": timedelta(days=-1),
            "candidates": [
                {
                    "type": "parameter_change",
                    "title": "温度 80℃ 暂定",
                    "description": "试探反应极限",
                    "parameters": [
                        {"name": "temperature", "value": "80", "unit": "℃"},
                        {"name": "time", "value": "2", "unit": "h"},
                    ],
                    "confidence": 0.75,
                },
            ],
            "transcript": [
                {"speaker": "陈工", "start_offset_sec": 5, "end_offset_sec": 15,
                 "text": "暂定尝试 80℃ 看看反应极限"},
            ],
        },
        {
            "mid": "meet_demo_70c",
            "title": "Compound-A 70℃ 复现实验评审",
            "delta": timedelta(hours=-2),
            "candidates": [
                {
                    "type": "parameter_change",
                    "title": "温度 70℃ 复现",
                    "description": "70℃ 收率优于 80℃",
                    "parameters": [
                        {"name": "temperature", "value": "70", "unit": "℃"},
                        {"name": "concentration", "value": "0.20", "unit": "mol/L"},
                        {"name": "time", "value": "2", "unit": "h"},
                    ],
                    "confidence": 0.92,
                },
            ],
            "transcript": [
                {"speaker": "陈博士", "start_offset_sec": 10, "end_offset_sec": 18,
                 "text": "复现实验确认 70℃ 收率更高"},
                {"speaker": "王工程师", "start_offset_sec": 20, "end_offset_sec": 30,
                 "text": "建议温度参数从 80 调整为 70"},
            ],
        },
        {
            "mid": "meet_demo_catalyst_08",
            "title": "Compound-A 催化剂 0.8 eq 复验讨论",
            "delta": timedelta(minutes=-30),
            "candidates": [
                {
                    "type": "parameter_change",
                    "title": "催化剂 0.8 eq 复验",
                    "description": "降低副产物",
                    "parameters": [
                        {"name": "temperature", "value": "70", "unit": "℃"},
                        {"name": "catalyst", "value": "0.8", "unit": "eq"},
                    ],
                    "confidence": 0.82,
                },
            ],
            "transcript": [
                {"speaker": "陈工", "start_offset_sec": 0, "end_offset_sec": 10,
                 "text": "副产物偏高，下一轮 catalyst 降到 0.8 eq 试试"},
                {"speaker": "李组长", "start_offset_sec": 15, "end_offset_sec": 20,
                 "text": "同意，保持温度 70℃ 不变"},
            ],
        },
    ]

    for sc in scenarios:
        captured = now + sc["delta"]
        m = Meeting(
            meeting_id=sc["mid"],
            experiment_id=exp.id,
            title=sc["title"],
            source="feishu_minutes",
            source_object_id=f"minutes_{sc['mid']}",
            source_url=f"https://feishu.example.com/minutes/{sc['mid']}",
            organizer="陈博士",
            participants=["陈博士", "王工程师", "孙研究员"],
            summary=sc["title"],
            transcript=sc["transcript"],
            captured_at=captured,
            raw_payload={"meeting_id": sc["mid"], "source": "feishu_mock"},
        )
        db.add(m)
        db.flush()

        db.add(MeetingReview(meeting_id=m.id, status="pending"))
        db.flush()

        cands = []
        for i, c in enumerate(sc["candidates"]):
            cands.append({
                "candidate_id": new_id("CDR"),
                "type": c["type"],
                "title": c["title"],
                "description": c.get("description"),
                "experiment_ref": "EXP-DEMO-001",
                "parameters": c.get("parameters", []),
                "confidence": c.get("confidence", 0.85),
                "evidence": [
                    {"speaker": t["speaker"], "text": t["text"],
                     "start_offset_sec": t["start_offset_sec"]}
                    for t in sc["transcript"]
                ],
                "status": "pending_review",
                "needs_review": True,
            })
        cand = Candidate(
            meeting_id=m.id,
            source_package_id=m.meeting_id,
            aily_skill_version="aily-labmemory-v1.0",
            candidates=cands,
            risks=[],
            action_items=[],
            open_questions=[],
            compiled_at=datetime.now(timezone.utc),
            raw_payload={},
        )
        db.add(cand)
        db.flush()

    # 实验二：保证重置后护照列表仍可见两个实验（实验本体与成员跨重置保留）
    exp2 = db.query(Experiment).filter(Experiment.experiment_id == "EXP-DEMO-002").first()
    if exp2 is not None:
        from scripts.seed_demo import _make_candidate as _mk_cand, _make_meeting as _mk_mtg
        m_b = _mk_mtg(
            db, exp2, "meet_demo_b_pending", "Compound-B 放大到 50L 结晶讨论",
            now - timedelta(minutes=40),
            transcript=[
                {"speaker": "陈工", "start_offset_sec": 0, "end_offset_sec": 12,
                 "text": "25℃ 工艺稳定，讨论放大到 50L 的传质问题"},
            ],
        )
        _mk_cand(db, m_b, [
            {"name": "cryst_temp", "value": "25", "unit": "℃"},
            {"name": "scale", "value": "50", "unit": "L"},
        ], "25℃ 放大至 50L", "验证传质与收率稳定性")

    db.add(AuditEvent(
        actor_id=actor.id, action="admin.reset_demo",
        target_type="system", target_id="EXP-DEMO-001",
        after={"mode": "pending"},
        reason="管理员重置演示数据",
    ))


def _seed_full_chain(db: Session, exp: Experiment, actor: User) -> None:
    """完整链路场景：复用 seed_demo.py 的场景函数，保证「重置为完整链路」与首次 seed 完全一致。

    覆盖两个实验的全部状态：已完成/阻断/冻结/待确认/运行中/待发布/已发布/已推翻/已结束。
    """
    from scripts.seed_demo import (
        ensure_experiment_2,
        seed_demo_data,
        seed_demo_data_exp2,
    )

    lead = db.query(User).filter(User.global_role == "lead").first()
    executor = db.query(User).filter(User.global_role == "executor").first()
    pi = db.query(User).filter(User.global_role == "pi").first()
    if not (lead and executor and pi):
        raise HTTPException(status_code=400, detail="缺少 pi / lead / executor 角色用户")

    users = {"pi": pi, "lead": lead, "executor": executor}
    exp2 = ensure_experiment_2(
        db, exp.project, owner=lead, members=[(pi, "pi"), (lead, "lead"), (executor, "executor")]
    )
    seed_demo_data(db, users, exp)
    seed_demo_data_exp2(db, users, exp2)

    db.add(AuditEvent(
        actor_id=actor.id, action="admin.reset_demo",
        target_type="system", target_id="EXP-DEMO-001",
        after={"mode": "full"},
        reason="管理员重置演示数据",
    ))
