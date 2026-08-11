"""初始化演示账号与基础项目/实验 + 端到端演示数据。

运行：
    conda run -n labmemory python -m scripts.seed_demo

幂等：重复运行不会重复创建或覆盖。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core.security import hash_password, new_id
from app.db.base import Base
from app.db.models import (
    ActionAudit,
    AuditEvent,
    Candidate,
    Claim,
    Experiment,
    ExperimentMember,
    Meeting,
    MeetingReview,
    Project,
    Result,
    Task,
    User,
)
from app.db.session import SessionLocal, engine


DEMO_USERS = [
    ("pi", "项目负责人（PI）", "pi"),
    ("lead", "实验负责人（Lead）", "lead"),
    ("executor", "执行人（Executor）", "executor"),
    ("admin", "管理员", "admin"),
]


def ensure_user(db, username: str, display: str, role: str) -> User:
    u = db.query(User).filter(User.username == username).first()
    if u is None:
        u = User(
            username=username,
            password_hash=hash_password("123456"),
            display_name=display,
            global_role=role,
            feishu_user_id=f"ou_{username}",  # 供 /api/v1/card/callback 的 open_id 映射
        )
        db.add(u)
        db.flush()
    return u


def ensure_project(db, pi: User) -> Project:
    p = db.query(Project).filter(Project.project_id == "PROJ-DEMO-001").first()
    if p is None:
        p = Project(
            project_id="PROJ-DEMO-001",
            name="晶研智流 Demo 项目",
            description="用于端到端测试的演示项目",
            pi_user_id=pi.id,
        )
        db.add(p)
        db.flush()
    return p


def ensure_experiment(db, proj: Project, owner: User, members: list[tuple[User, str]]) -> Experiment:
    e = db.query(Experiment).filter(Experiment.experiment_id == "EXP-DEMO-001").first()
    if e is None:
        e = Experiment(
            experiment_id="EXP-DEMO-001",
            project_id=proj.id,
            name="Compound-A 合成优化实验",
            owner_user_id=owner.id,
            parameters_template=None,
        )
        db.add(e)
        db.flush()
    for u, role in members:
        existing = db.query(ExperimentMember).filter(
            ExperimentMember.experiment_id == e.id,
            ExperimentMember.user_id == u.id,
        ).first()
        if existing is None:
            db.add(ExperimentMember(experiment_id=e.id, user_id=u.id, role=role))
    return e


def _make_meeting(db, exp: Experiment, meeting_id: str, title: str, captured_at: datetime, transcript: list) -> Meeting:
    m = db.query(Meeting).filter(Meeting.meeting_id == meeting_id).first()
    if m is None:
        m = Meeting(
            meeting_id=meeting_id,
            experiment_id=exp.id,
            title=title,
            source="feishu_minutes",
            source_object_id=f"minute_{meeting_id}",
            source_url=f"https://feishu.example.com/minutes/{meeting_id}",
            organizer="陈博士",
            participants=["陈博士", "王工程师", "孙研究员"],
            summary=title,
            transcript=transcript,
            captured_at=captured_at,
            raw_payload={"meeting_id": meeting_id, "title": title},
        )
        db.add(m)
        db.flush()
        db.add(MeetingReview(meeting_id=m.id, status="pending"))
        db.flush()
    return m


def _make_candidate(db, meeting: Meeting, parameters: list[dict], title: str, description: str) -> Candidate:
    cand = db.query(Candidate).filter(Candidate.meeting_id == meeting.id).first()
    if cand is None:
        cand = Candidate(
            meeting_id=meeting.id,
            source_package_id=meeting.meeting_id,
            aily_skill_version="aily-labmemory-v1.0",
            candidates=[{
                "candidate_id": new_id("CDR"),
                "type": "parameter_change",
                "title": title,
                "description": description,
                "experiment_ref": "EXP-DEMO-001",
                "parameters": parameters,
                "confidence": 0.9,
                "evidence": [],
                "status": "pending_review",
                "needs_review": True,
            }],
            risks=[],
            action_items=[],
            open_questions=[],
            compiled_at=datetime.utcnow(),
            raw_payload={},
        )
        db.add(cand)
        db.flush()
    return cand


def _confirm_review(db, meeting: Meeting, exp: Experiment, reviewer: User, modifications: dict | None = None) -> tuple[Claim, Task]:
    """模拟复核确认：生成主张 + 任务草稿。"""
    r = db.query(MeetingReview).filter(MeetingReview.meeting_id == meeting.id).first()
    r.status = "processed"
    r.decision = "confirmed"
    r.reviewer_id = reviewer.id
    r.reviewed_at = datetime.utcnow()
    r.modifications = modifications

    cand = db.query(Candidate).filter(Candidate.meeting_id == meeting.id).first()
    chosen = (cand.candidates or [{}])[0]
    old_active = (
        db.query(Claim)
        .filter(Claim.experiment_id == exp.id, Claim.status == "current")
        .order_by(Claim.created_at.desc())
        .first()
    )
    version_no = 1
    replaces_id = None
    if old_active is not None:
        old_active.status = "superseded"
        replaces_id = old_active.id
        old_pv = old_active.parameter_version or {}
        try:
            version_no = int(old_pv.get("version", "v1").lstrip("v")) + 1
        except (ValueError, AttributeError):
            version_no = 2

    params = modifications.get("parameters") if modifications else chosen.get("parameters", [])
    claim = Claim(
        claim_id=new_id("C"),
        meeting_id=meeting.id,
        experiment_id=exp.id,
        content={
            "title": chosen.get("title", meeting.title),
            "description": chosen.get("description"),
            "type": chosen.get("type"),
            "experiment_ref": chosen.get("experiment_ref"),
            "evidence": chosen.get("evidence", []),
            "confidence": chosen.get("confidence"),
        },
        parameter_version={
            "parameters": params,
            "version": f"v{version_no}",
            "effective_at": datetime.utcnow().isoformat(),
            "scope": modifications.get("scope") if modifications else None,
        },
        status="current",
        replaces_claim_id=replaces_id,
    )
    db.add(claim)
    db.flush()
    task = Task(
        task_id=new_id("T"),
        meeting_id=meeting.id,
        experiment_id=exp.id,
        claim_id=claim.id,
        status="draft",
        planned_params=claim.parameter_version,
    )
    db.add(task)
    db.flush()
    db.add(AuditEvent(
        actor_id=reviewer.id, action="review.confirmed",
        target_type="meeting", target_id=meeting.meeting_id,
        after={"claim_id": claim.claim_id, "task_id": task.task_id},
    ))
    db.flush()
    return claim, task


def _run_audit(db, task: Task, auditor: User, passed: bool) -> ActionAudit:
    """模拟行动前审计。"""
    checks = {
        "version_unit": {"status": "passed" if passed else "failed", "message": "版本有效" if passed else "引用已过期版本"},
        "evidence_scope": {"status": "passed", "message": "证据可定位"},
        "approval": {"status": "passed", "message": "已授权"},
        "resource": {"status": "passed", "message": "物料设备可用"},
        "failure_boundary": {"status": "passed", "message": "无失败边界命中"},
    }
    a = ActionAudit(
        task_id=task.id,
        status="passed" if passed else "blocked",
        auditor_id=auditor.id,
        audited_at=datetime.utcnow(),
        checks=checks,
        result={"overall": "pass" if passed else "blocked", "reason": "" if passed else "引用已过期参数版本"},
    )
    db.add(a)
    db.flush()
    db.add(AuditEvent(
        actor_id=auditor.id, action="task.audited",
        target_type="task", target_id=task.task_id,
        after={"status": a.status},
    ))
    db.flush()
    return a


def _submit_and_publish(db, task: Task, claim: Claim, submitter: User, publisher: User, metrics: dict, knowledge_status: str, failure_boundary: dict | None = None) -> Result:
    """模拟结果提交 + 发布。"""
    task.status = "running"
    db.flush()
    task.status = "completed"
    db.flush()
    res = Result(
        result_id=new_id("R"),
        task_id=task.id,
        submitter_id=submitter.id,
        actual_params={p["name"]: {"value": p["value"], "unit": p.get("unit")} for p in (claim.parameter_version.get("parameters") if claim.parameter_version else [])},
        metrics=metrics,
        files=[],
        status="submitted",
    )
    db.add(res)
    db.flush()
    db.add(AuditEvent(
        actor_id=submitter.id, action="result.submitted",
        target_type="result", target_id=res.result_id,
    ))
    db.flush()
    res.status = "published"
    res.publisher_id = publisher.id
    res.published_at = datetime.utcnow()
    res.knowledge_status = knowledge_status
    res.failure_boundary = failure_boundary
    claim.knowledge_status = knowledge_status
    db.flush()
    db.add(AuditEvent(
        actor_id=publisher.id, action="result.published",
        target_type="result", target_id=res.result_id,
        after={"knowledge_status": knowledge_status},
    ))
    db.flush()
    return res


def seed_demo_data(db, users: dict[str, User], exp: Experiment) -> None:
    """创建演示数据：已完成实验链 + 阻断任务 + pending 复核。"""
    # 检查是否已有 seed 数据
    if db.query(Meeting).filter(Meeting.meeting_id == "meet_seed_completed").first():
        return

    now = datetime.utcnow()

    # === 已完成实验链：60℃ -> 65℃，部分支持 ===
    m1 = _make_meeting(
        db, exp, "meet_seed_completed", "Compound-A 60→65℃ 升温评审",
        now - timedelta(days=2),
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 10, "end_offset_sec": 18, "text": "上一轮 60℃ 转化率只有 63%，建议升到 65℃"},
            {"speaker": "赵负责人", "start_offset_sec": 20, "end_offset_sec": 30, "text": "同意，验收看转化率≥75%且副产物≤6%"},
        ],
    )
    _make_candidate(db, m1, [
        {"name": "temperature", "value": "65", "unit": "℃"},
        {"name": "time", "value": "2", "unit": "h"},
        {"name": "catalyst", "value": "1.0", "unit": "eq"},
    ], "温度 60→65℃ 升温", "提升转化率")
    claim1, task1 = _confirm_review(db, m1, exp, users["lead"])
    _run_audit(db, task1, users["lead"], passed=True)
    _submit_and_publish(
        db, task1, claim1, users["executor"], users["lead"],
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

    # === 阻断任务场景：旧 80℃ 任务被新 70℃ 主张阻断 ===
    # 第二次会议：80℃ 主张（v2，supersede 65℃ 的 v1）
    m2 = _make_meeting(
        db, exp, "meet_seed_80c", "Compound-A 80℃ 暂定参数评审",
        now - timedelta(days=1),
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 5, "end_offset_sec": 15, "text": "暂定尝试 80℃ 看看反应极限"},
        ],
    )
    _make_candidate(db, m2, [
        {"name": "temperature", "value": "80", "unit": "℃"},
        {"name": "time", "value": "2", "unit": "h"},
    ], "温度 80℃ 暂定", "试探反应极限")
    claim2_80, task2_80 = _confirm_review(db, m2, exp, users["lead"])
    # task2_80 引用 claim2_80（80℃），保持 draft 状态

    # 第三次会议：70℃ 复现实验，supersede 80℃
    m3 = _make_meeting(
        db, exp, "meet_seed_70c", "Compound-A 70℃ 复现实验评审",
        now - timedelta(hours=2),
        transcript=[
            {"speaker": "陈博士", "start_offset_sec": 10, "end_offset_sec": 18, "text": "复现实验确认 70℃ 收率更高"},
            {"speaker": "王工程师", "start_offset_sec": 20, "end_offset_sec": 30, "text": "建议温度参数从 80 调整为 70"},
        ],
    )
    _make_candidate(db, m3, [
        {"name": "temperature", "value": "70", "unit": "℃"},
        {"name": "concentration", "value": "0.20", "unit": "mol/L"},
        {"name": "time", "value": "2", "unit": "h"},
    ], "温度 70℃ 复现", "70℃ 收率优于 80℃")
    claim3_70, task3_70 = _confirm_review(db, m3, exp, users["lead"])
    # 此时 claim3_70 是 current，claim2_80 被 superseded
    # task2_80 仍引用 claim2_80（superseded）-> audit 应阻断
    _run_audit(db, task2_80, users["lead"], passed=False)
    task2_80.status = "blocked"

    # === pending 复核会议 ===
    _make_meeting(
        db, exp, "meet_seed_pending", "Compound-A 催化剂 0.8 eq 复验讨论",
        now - timedelta(minutes=30),
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 0, "end_offset_sec": 10, "text": "副产物偏高，下一轮 catalyst 降到 0.8 eq 试试"},
        ],
    )
    m_pending = db.query(Meeting).filter(Meeting.meeting_id == "meet_seed_pending").first()
    _make_candidate(db, m_pending, [
        {"name": "temperature", "value": "70", "unit": "℃"},
        {"name": "catalyst", "value": "0.8", "unit": "eq"},
    ], "催化剂 0.8 eq 复验", "降低副产物")


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        users = {u: ensure_user(db, u, d, r) for u, d, r in DEMO_USERS}
        proj = ensure_project(db, users["pi"])
        exp = ensure_experiment(
            db,
            proj,
            owner=users["lead"],
            members=[
                (users["pi"], "pi"),
                (users["lead"], "lead"),
                (users["executor"], "executor"),
            ],
        )
        seed_demo_data(db, users, exp)
        db.commit()
        print("✓ 演示数据已初始化")
        print("  账号: pi / lead / executor / admin（密码均为 123456）")
        print("  项目: PROJ-DEMO-001")
        print("  实验: EXP-DEMO-001")
        print("  演示场景:")
        print("    - meet_seed_completed: 已完成实验链（65℃ 部分支持，含失败边界卡）")
        print("    - meet_seed_80c -> meet_seed_70c: 80℃ 任务被 70℃ 主张阻断")
        print("    - meet_seed_pending: 待复核会议（0.8 eq 复验）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
