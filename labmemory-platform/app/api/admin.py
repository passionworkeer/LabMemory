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
    if user.global_role not in ("admin", "pi"):
        # PI 也允许重置演示数据，方便 Demo 演示
        from app.core.errors import PermissionDeniedError
        raise PermissionDeniedError("仅管理员或 PI 可重置演示数据")
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
    return {"status": "ok", "mode": mode, "message": f"演示数据已重置（{mode} 模式）"}


def _seed_pending_only(db: Session, exp: Experiment, actor: User) -> None:
    """模拟飞书推送：4 个待复核会议（无已处理数据）。

    这些会议后续需要用户在前端手动确认，才能推进链路。
    """
    now = datetime.utcnow()

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
            compiled_at=datetime.utcnow(),
            raw_payload={},
        )
        db.add(cand)
        db.flush()

    db.add(AuditEvent(
        actor_id=actor.id, action="admin.reset_demo",
        target_type="system", target_id="EXP-DEMO-001",
        after={"mode": "pending"},
        reason="管理员重置演示数据",
    ))


def _seed_full_chain(db: Session, exp: Experiment, actor: User) -> None:
    """完整链路场景：已完成 + 已阻断 + 待复核（直接写库，不依赖前端操作）。

    与 seed_demo.py 的场景保持一致，但通过这里的函数实现。
    """
    from scripts.seed_demo import (
        _confirm_review,
        _make_candidate,
        _make_meeting,
        _run_audit,
        _submit_and_publish,
    )

    # 找一个 lead 用户作为复核/发布者
    lead = db.query(User).filter(User.global_role == "lead").first()
    executor = db.query(User).filter(User.global_role == "executor").first()
    if not lead or not executor:
        raise HTTPException(status_code=400, detail="缺少 lead / executor 角色用户")

    now = datetime.utcnow()

    # 场景 1：已完成实验链
    m1 = _make_meeting(
        db, exp, "meet_full_65c", "Compound-A 60→65℃ 升温评审",
        now - timedelta(days=2),
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 10, "end_offset_sec": 18,
             "text": "上一轮 60℃ 转化率只有 63%，建议升到 65℃"},
            {"speaker": "赵负责人", "start_offset_sec": 20, "end_offset_sec": 30,
             "text": "同意，验收看转化率≥75%且副产物≤6%"},
        ],
    )
    _make_candidate(db, m1, [
        {"name": "temperature", "value": "65", "unit": "℃"},
        {"name": "time", "value": "2", "unit": "h"},
        {"name": "catalyst", "value": "1.0", "unit": "eq"},
    ], "温度 60→65℃ 升温", "提升转化率")
    claim1, task1 = _confirm_review(db, m1, exp, lead)
    _run_audit(db, task1, lead, passed=True)
    _submit_and_publish(
        db, task1, claim1, executor, lead,
        metrics={"conversion": "78%", "byproduct": "9%"},
        knowledge_status="partially_supported",
        failure_boundary={
            "phenomenon": "副产物升至 9%",
            "trigger_condition": "65℃ / 2h / 1.0 eq",
            "ruled_out": "物料批次、仪器校准",
            "root_cause_status": "高温×催化剂当量共同作用（待验证）",
            "next_step": "65℃ / 0.8 eq 复验",
        },
    )

    # 场景 2：80℃ 被阻断任务
    m2 = _make_meeting(
        db, exp, "meet_full_80c", "Compound-A 80℃ 暂定参数评审",
        now - timedelta(days=1),
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 5, "end_offset_sec": 15,
             "text": "暂定尝试 80℃ 看看反应极限"},
        ],
    )
    _make_candidate(db, m2, [
        {"name": "temperature", "value": "80", "unit": "℃"},
        {"name": "time", "value": "2", "unit": "h"},
    ], "温度 80℃ 暂定", "试探反应极限")
    claim2, task2 = _confirm_review(db, m2, exp, lead)
    # task2 保持 draft 状态 —— 注意 claim2 此时还是 current

    # 场景 3：70℃ 复现（supersede 80℃）
    m3 = _make_meeting(
        db, exp, "meet_full_70c", "Compound-A 70℃ 复现实验评审",
        now - timedelta(hours=2),
        transcript=[
            {"speaker": "陈博士", "start_offset_sec": 10, "end_offset_sec": 18,
             "text": "复现实验确认 70℃ 收率更高"},
            {"speaker": "王工程师", "start_offset_sec": 20, "end_offset_sec": 30,
             "text": "建议温度参数从 80 调整为 70"},
        ],
    )
    _make_candidate(db, m3, [
        {"name": "temperature", "value": "70", "unit": "℃"},
        {"name": "concentration", "value": "0.20", "unit": "mol/L"},
        {"name": "time", "value": "2", "unit": "h"},
    ], "温度 70℃ 复现", "70℃ 收率优于 80℃")
    claim3, task3 = _confirm_review(db, m3, exp, lead)
    # claim3 是 current，claim2 已被 superseded
    # task2 引用 claim2（旧），审计会阻断
    _run_audit(db, task2, lead, passed=False)
    task2.status = "blocked"

    # 场景 4：待复核
    _make_meeting(
        db, exp, "meet_full_pending", "Compound-A 催化剂 0.8 eq 复验讨论",
        now - timedelta(minutes=30),
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 0, "end_offset_sec": 10,
             "text": "副产物偏高，下一轮 catalyst 降到 0.8 eq 试试"},
        ],
    )
    m_pending = db.query(Meeting).filter(Meeting.meeting_id == "meet_full_pending").first()
    _make_candidate(db, m_pending, [
        {"name": "temperature", "value": "70", "unit": "℃"},
        {"name": "catalyst", "value": "0.8", "unit": "eq"},
    ], "催化剂 0.8 eq 复验", "降低副产物")

    db.add(AuditEvent(
        actor_id=actor.id, action="admin.reset_demo",
        target_type="system", target_id="EXP-DEMO-001",
        after={"mode": "full"},
        reason="管理员重置演示数据",
    ))
