"""初始化演示账号与基础项目/实验 + 端到端演示数据。

运行：
    conda run -n labmemory python -m scripts.seed_demo

幂等：重复运行不会重复创建或覆盖。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def ensure_experiment_2(db, proj: Project, owner: User, members: list[tuple[User, str]]) -> Experiment:
    """第二个演示实验：承载「已验证 / 已推翻」闭环，避免与 EXP-DEMO-001 的迭代链互相覆盖。"""
    e = db.query(Experiment).filter(Experiment.experiment_id == "EXP-DEMO-002").first()
    if e is None:
        e = Experiment(
            experiment_id="EXP-DEMO-002",
            project_id=proj.id,
            name="Compound-B 结晶纯化工艺优化",
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
            compiled_at=datetime.now(timezone.utc),
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
    r.reviewed_at = datetime.now(timezone.utc)
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
            "effective_at": datetime.now(timezone.utc).isoformat(),
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
        audited_at=datetime.now(timezone.utc),
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
    res.published_at = datetime.now(timezone.utc)
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


def _end_review(db, meeting: Meeting, reviewer: User, reason: str = "") -> None:
    """模拟复核直接结束（decision=ended，不进入数据链路、不生成主张/任务）。"""
    r = db.query(MeetingReview).filter(MeetingReview.meeting_id == meeting.id).first()
    r.status = "processed"
    r.decision = "ended"
    r.reviewer_id = reviewer.id
    r.reviewed_at = datetime.now(timezone.utc)
    r.notes = reason or None
    db.add(AuditEvent(
        actor_id=reviewer.id, action="review.ended",
        target_type="meeting", target_id=meeting.meeting_id,
        reason=reason or None,
    ))
    db.flush()


def _audit_needs_confirmation(db, task: Task, auditor: User, message: str = "命中未解决失败边界，需确认知晓") -> ActionAudit:
    """模拟行动前审计停在 needs_confirmation（失败边界门未确认）。"""
    checks = {
        "version_unit": {"status": "passed", "message": "版本有效"},
        "evidence_scope": {"status": "passed", "message": "证据可定位"},
        "approval": {"status": "passed", "message": "已授权"},
        "resource": {"status": "passed", "message": "物料设备可用"},
        "failure_boundary": {"status": "needs_confirmation", "message": message},
    }
    a = ActionAudit(
        task_id=task.id,
        status="needs_confirmation",
        auditor_id=auditor.id,
        audited_at=datetime.now(timezone.utc),
        checks=checks,
        result={"overall": "needs_confirmation", "reason": message},
    )
    db.add(a)
    db.flush()
    task.status = "needs_confirmation"
    db.add(AuditEvent(
        actor_id=auditor.id, action="task.audited",
        target_type="task", target_id=task.task_id,
        after={"status": a.status},
    ))
    db.flush()
    return a


def _submit_only(db, task: Task, claim: Claim, submitter: User, actual_params: dict, metrics: dict, failure_boundary: dict | None = None) -> Result:
    """模拟结果已提交但尚未发布（status=submitted，等待 PI/Lead 发布为知识）。"""
    task.status = "running"
    db.flush()
    task.status = "completed"
    db.flush()
    res = Result(
        result_id=new_id("R"),
        task_id=task.id,
        submitter_id=submitter.id,
        actual_params=actual_params,
        metrics=metrics,
        files=[],
        status="submitted",
        failure_boundary=failure_boundary,
    )
    db.add(res)
    db.flush()
    db.add(AuditEvent(
        actor_id=submitter.id, action="result.submitted",
        target_type="result", target_id=res.result_id,
    ))
    db.flush()
    return res


def _submit_frozen(db, task: Task, submitter: User, actual_params: dict, metrics: dict, reason: str = "实际参数含计划外项，与计划版本不匹配") -> Result:
    """模拟结果冻结（status=frozen，参数偏离计划版本，不进入知识生成）。"""
    task.status = "running"
    db.flush()
    task.status = "completed"
    db.flush()
    res = Result(
        result_id=new_id("R"),
        task_id=task.id,
        submitter_id=submitter.id,
        actual_params=actual_params,
        metrics=metrics,
        files=[],
        status="frozen",
        notes=reason,
    )
    db.add(res)
    db.flush()
    db.add(AuditEvent(
        actor_id=submitter.id, action="result.submitted",
        target_type="result", target_id=res.result_id,
        after={"status": "frozen"},
    ))
    db.flush()
    return res


def _mark_running(db, task: Task, approver: User, assignee: User) -> None:
    """模拟审计通过后启动执行（status=running，审批/资源/失败边界门均已通过）。"""
    task.approval_status = "approved"
    task.approved_by = approver.id
    task.approved_at = datetime.now(timezone.utc)
    task.resource_status = "ready"
    task.failure_boundary_ack = True
    task.assignee_id = assignee.id
    task.status = "running"
    db.flush()
    db.add(AuditEvent(
        actor_id=approver.id, action="task.started",
        target_type="task", target_id=task.task_id,
        after={"status": "running"},
    ))
    db.flush()


def seed_demo_data(db, users: dict[str, User], exp: Experiment) -> None:
    """创建演示数据：已完成实验链 + 阻断任务 + pending 复核。"""
    # 检查是否已有 seed 数据
    if db.query(Meeting).filter(Meeting.meeting_id == "meet_seed_completed").first():
        return

    now = datetime.now(timezone.utc)

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

    # === 冻结结果：实际参数含计划外项 → frozen（不进入知识） ===
    m_frozen = _make_meeting(
        db, exp, "meet_seed_frozen", "Compound-A 溶剂体系切换评审",
        now - timedelta(minutes=110),
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 5, "end_offset_sec": 14, "text": "试试把溶剂换成乙醇/水混合体系看选择性"},
        ],
    )
    _make_candidate(db, m_frozen, [
        {"name": "temperature", "value": "70", "unit": "℃"},
        {"name": "time", "value": "2", "unit": "h"},
    ], "溶剂体系切换", "乙醇/水混合溶剂")
    _, task_frozen = _confirm_review(db, m_frozen, exp, users["lead"])
    _run_audit(db, task_frozen, users["lead"], passed=True)
    _submit_frozen(
        db, task_frozen, users["executor"],
        actual_params={
            "temperature": {"value": "70", "unit": "℃"},
            "time": {"value": "2", "unit": "h"},
            "solvent_ratio": {"value": "3:1", "unit": "v/v"},  # 计划外项 → 冻结
        },
        metrics={"conversion": "72%", "byproduct": "5%"},
    )

    # === needs_confirmation 任务：命中未解决失败边界，需确认 ===
    m_nc = _make_meeting(
        db, exp, "meet_seed_needs_conf", "Compound-A 65℃ 边界复评讨论",
        now - timedelta(minutes=95),
        transcript=[
            {"speaker": "王工程师", "start_offset_sec": 0, "end_offset_sec": 12, "text": "65℃ 副产物偏高的边界还没闭环，再跑要先确认风险"},
        ],
    )
    _make_candidate(db, m_nc, [
        {"name": "temperature", "value": "65", "unit": "℃"},
        {"name": "catalyst", "value": "0.9", "unit": "eq"},
    ], "65℃ 边界复评", "确认高温副产物风险后执行")
    _, task_nc = _confirm_review(db, m_nc, exp, users["lead"])
    _audit_needs_confirmation(db, task_nc, users["lead"])

    # === 已提交待发布结果：执行人已提交，等 PI/Lead 发布 ===
    m_sub = _make_meeting(
        db, exp, "meet_seed_submitted", "Compound-A 搅拌转速优化评审",
        now - timedelta(minutes=80),
        transcript=[
            {"speaker": "孙研究员", "start_offset_sec": 4, "end_offset_sec": 16, "text": "转速从 400 提到 600 rpm，混合更均匀"},
        ],
    )
    _make_candidate(db, m_sub, [
        {"name": "stir_speed", "value": "600", "unit": "rpm"},
        {"name": "temperature", "value": "70", "unit": "℃"},
    ], "搅拌转速 600 rpm", "改善混合均匀度")
    claim_sub, task_sub = _confirm_review(db, m_sub, exp, users["lead"])
    _run_audit(db, task_sub, users["lead"], passed=True)
    _submit_only(
        db, task_sub, claim_sub, users["executor"],
        actual_params={
            "stir_speed": {"value": "600", "unit": "rpm"},
            "temperature": {"value": "70", "unit": "℃"},
        },
        metrics={"conversion": "81%", "byproduct": "5.5%"},
    )

    # === 运行中任务（当前主张）：审计通过、已启动、尚未提交结果 ===
    m_run = _make_meeting(
        db, exp, "meet_seed_running", "Compound-A 70℃/0.8 eq 5L 放大评审",
        now - timedelta(minutes=15),
        transcript=[
            {"speaker": "陈博士", "start_offset_sec": 6, "end_offset_sec": 18, "text": "前几轮 70℃ 配 0.8 eq 副产物可控，放大到 5L 验证"},
            {"speaker": "赵负责人", "start_offset_sec": 20, "end_offset_sec": 28, "text": "同意放大，注意传热滞后"},
        ],
    )
    _make_candidate(db, m_run, [
        {"name": "temperature", "value": "70", "unit": "℃"},
        {"name": "catalyst", "value": "0.8", "unit": "eq"},
        {"name": "scale", "value": "5", "unit": "L"},
    ], "70℃/0.8 eq 5L 放大", "规模放大验证")
    _, task_run = _confirm_review(db, m_run, exp, users["lead"])
    _run_audit(db, task_run, users["lead"], passed=True)
    _mark_running(db, task_run, users["lead"], users["executor"])

    # === ended 复核：分析方法调整，非工艺参数变更，直接结束 ===
    m_ended = _make_meeting(
        db, exp, "meet_seed_ended", "Compound-A 紫外检测波长讨论（非参数变更）",
        now - timedelta(minutes=50),
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 0, "end_offset_sec": 10, "text": "检测波长从 254 换 210 只是分析方法调整，不改工艺参数"},
        ],
    )
    _make_candidate(db, m_ended, [
        {"name": "uv_wavelength", "value": "210", "unit": "nm"},
    ], "检测波长 210 nm", "分析方法调整（非工艺）")
    _end_review(db, m_ended, users["lead"], reason="非工艺参数变更，不进入实验链路")


def seed_demo_data_exp2(db, users: dict[str, User], exp: Experiment) -> None:
    """实验二 Compound-B：已推翻(refuted) → 已验证(supported) 的闭环演示。

    current 主张为 supported（绿），历史含一条 refuted（红）与模型偏差卡，
    用于覆盖可信问答的「已验证/已推翻」权重与护照徽标。
    """
    if db.query(Meeting).filter(Meeting.meeting_id == "meet_seed_b_refuted").first():
        return

    now = datetime.now(timezone.utc)

    # B1 已推翻链（较早）：降温结晶假设被实验推翻
    m_ref = _make_meeting(
        db, exp, "meet_seed_b_refuted", "Compound-B 降温结晶收率假设评审",
        now - timedelta(days=3),
        transcript=[
            {"speaker": "陈博士", "start_offset_sec": 8, "end_offset_sec": 18, "text": "假设降温到 10℃ 能把收率提到 85%"},
            {"speaker": "王工程师", "start_offset_sec": 20, "end_offset_sec": 28, "text": "先按这个跑一发验证"},
        ],
    )
    _make_candidate(db, m_ref, [
        {"name": "cryst_temp", "value": "10", "unit": "℃"},
        {"name": "hold_time", "value": "4", "unit": "h"},
    ], "降温至 10℃ 结晶", "假设可提升收率至 85%")
    claim_ref, task_ref = _confirm_review(db, m_ref, exp, users["lead"])
    _run_audit(db, task_ref, users["lead"], passed=True)
    res_ref = _submit_and_publish(
        db, task_ref, claim_ref, users["executor"], users["lead"],
        metrics={"recovery": "41%", "purity": "92%"},
        knowledge_status="refuted",
    )
    res_ref.model_feedback = {
        "model_version": "predictor-v2",
        "prediction": {"recovery": "85%"},
        "actual": {"recovery": "41%"},
        "deviation_type": "overestimate",
        "feedback_task": None,
    }
    res_ref.notes = "降温结晶假设被实验推翻：实际收率远低于预测"
    db.flush()

    # B2 已验证链（较新，成为 current）：程序降温 + 闭环失败边界
    m_sup = _make_meeting(
        db, exp, "meet_seed_b_supported", "Compound-B 25℃ 程序降温结晶评审",
        now - timedelta(days=1),
        transcript=[
            {"speaker": "陈博士", "start_offset_sec": 6, "end_offset_sec": 16, "text": "25℃ 配 0.2℃/min 缓慢降温，收率稳定 88%、纯度 99%"},
            {"speaker": "赵负责人", "start_offset_sec": 18, "end_offset_sec": 26, "text": "之前高温快冷析出多晶型的边界已通过溶剂配比闭环"},
        ],
    )
    _make_candidate(db, m_sup, [
        {"name": "cryst_temp", "value": "25", "unit": "℃"},
        {"name": "hold_time", "value": "6", "unit": "h"},
        {"name": "cooling_rate", "value": "0.2", "unit": "℃/min"},
    ], "25℃ 程序降温结晶", "收率 88% / 纯度 99%，边界已闭环")
    claim_sup, task_sup = _confirm_review(db, m_sup, exp, users["lead"])
    _run_audit(db, task_sup, users["lead"], passed=True)
    _submit_and_publish(
        db, task_sup, claim_sup, users["executor"], users["lead"],
        metrics={"purity": "99.1%", "recovery": "88%"},
        knowledge_status="supported",
        failure_boundary={
            "phenomenon": "高温快冷析出多晶型",
            "trigger_condition": "降温速率 ≥ 1℃/min",
            "ruled_out": "原料批次、操作人员",
            "root_cause_status": "已闭环",
            "next_step": "程序降温 0.2℃/min 已固化进 SOP",
        },
    )

    # B3 待复核会议
    _make_meeting(
        db, exp, "meet_seed_b_pending", "Compound-B 放大到 50L 结晶讨论",
        now - timedelta(minutes=40),
        transcript=[
            {"speaker": "陈工", "start_offset_sec": 0, "end_offset_sec": 12, "text": "25℃ 工艺稳定，讨论放大到 50L 的传质问题"},
        ],
    )
    m_b_pending = db.query(Meeting).filter(Meeting.meeting_id == "meet_seed_b_pending").first()
    _make_candidate(db, m_b_pending, [
        {"name": "cryst_temp", "value": "25", "unit": "℃"},
        {"name": "scale", "value": "50", "unit": "L"},
    ], "25℃ 放大至 50L", "验证传质与收率稳定性")


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
        exp2 = ensure_experiment_2(
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
        seed_demo_data_exp2(db, users, exp2)
        db.commit()

        # 演示数据初始化后全量重建 RAG 索引
        try:
            from app.db import vec
            from app.config import settings
            from app.services.indexer import reindex_all
            vec.ensure_vec_tables(db, settings.QWEN_EMBEDDING_DIM)
            stats = reindex_all(db)
            db.commit()
            print(f"✓ RAG 索引已重建：claims={stats['claims']} results={stats['results']} "
                  f"evidence={stats['evidence']} boundaries={stats['boundaries']}")
        except Exception as e:
            print(f"⚠ RAG 索引重建失败（不阻断 seed）：{e}")

        print("✓ 演示数据已初始化")
        print("  账号: pi / lead / executor / admin（密码均为 123456）")
        print("  项目: PROJ-DEMO-001")
        print("  实验: EXP-DEMO-001（Compound-A 合成优化，迭代中）/ EXP-DEMO-002（Compound-B 结晶纯化，已闭环）")
        print("  EXP-DEMO-001 演示场景:")
        print("    - meet_seed_completed: 已完成实验链（65℃ 部分支持，含失败边界卡）")
        print("    - meet_seed_80c -> meet_seed_70c: 80℃ 任务被 70℃ 主张阻断")
        print("    - meet_seed_frozen: 结果冻结（实际参数含计划外项）")
        print("    - meet_seed_needs_conf: 审计停在 needs_confirmation（失败边界未确认）")
        print("    - meet_seed_submitted: 结果已提交待发布")
        print("    - meet_seed_running: 当前主张运行中任务（尚未提交结果）")
        print("    - meet_seed_ended: 复核直接结束（非工艺变更）")
        print("    - meet_seed_pending: 待复核会议（0.8 eq 复验）")
        print("  EXP-DEMO-002 演示场景:")
        print("    - meet_seed_b_refuted: 已推翻知识（降温假设被证伪，含模型偏差卡）")
        print("    - meet_seed_b_supported: 当前主张已验证（25℃ 程序降温，失败边界已闭环）")
        print("    - meet_seed_b_pending: 待复核会议（50L 放大）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
