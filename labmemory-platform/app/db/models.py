"""领域模型。

设计要点（与用户简化需求对齐）：
- 三角色：PI / Lead / Executor 都能操作 复核 / 审计 / 回流 / 护照；仅 PI 管理实验；仅 PI/Lead 发布知识。
- 跟踪链：experiment_id 跨会议统一跟踪；meeting_id 跟踪单次会议操作；一个会议最终形成一个任务。
- 参数不硬编码：候选 / 主张 / 任务 / 结果的参数 JSON 完全由会议传入数据决定。
- 状态机：复核 pending/processed；审计 pending/passed/blocked；任务 draft/running/completed/blocked；结果 submitted/published/frozen。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IDMixin, TimestampMixin


# === 用户与项目 ===

class User(Base, IDMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    feishu_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # 全局角色：admin / pi / lead / executor（仅用于平台登录的默认身份）
    # 业务权限以 ExperimentMember.role 为准（PI/Lead/Executor 三种）。
    global_role: Mapped[str] = mapped_column(String(32), default="executor", nullable=False)


class Project(Base, IDMixin, TimestampMixin):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pi_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    experiments: Mapped[list[Experiment]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Experiment(Base, IDMixin, TimestampMixin):
    __tablename__ = "experiments"

    experiment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # 参数模板（可空）：由会议传入数据动态填充，不硬编码。
    parameters_template: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    project: Mapped[Project] = relationship(back_populates="experiments")
    members: Mapped[list[ExperimentMember]] = relationship(back_populates="experiment", cascade="all, delete-orphan")


class ExperimentMember(Base, IDMixin, TimestampMixin):
    __tablename__ = "experiment_members"
    __table_args__ = (UniqueConstraint("experiment_id", "user_id", name="uq_exp_member"),)

    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # pi / lead / executor：业务角色（决定能否操作实验管理、能否发布知识）
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    experiment: Mapped[Experiment] = relationship(back_populates="members")


# === 会议接入与候选 ===

class Meeting(Base, IDMixin, TimestampMixin):
    __tablename__ = "meetings"

    meeting_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="feishu_minutes", nullable=False)
    source_object_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    organizer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    participants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[list | None] = mapped_column(JSON, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 飞书原始 MeetingPackage（保留以便追溯）
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Candidate(Base, IDMixin, TimestampMixin):
    """Aily 编译后的候选决策包，每个会议最多一条最新候选。"""
    __tablename__ = "candidates"
    __table_args__ = (UniqueConstraint("meeting_id", "source_package_id", name="uq_meeting_pkg"),)

    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False, index=True)
    source_package_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    aily_skill_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 候选列表（来自 CandidatePackage.candidates）
    candidates: Mapped[list | None] = mapped_column(JSON, nullable=True)
    risks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    action_items: Mapped[list | None] = mapped_column(JSON, nullable=True)
    open_questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    compiled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# === 会后复核 ===

class MeetingReview(Base, IDMixin, TimestampMixin):
    """会后复核：一个会议一条复核记录。状态简化为 pending/processed。"""
    __tablename__ = "meeting_reviews"
    __table_args__ = (UniqueConstraint("meeting_id", name="uq_review_per_meeting"),)

    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    # decision: confirmed（确认/修改后确认，进入数据链路）/ ended（直接结束，不进入后续）
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 复核时的修改（参数覆盖、范围修正等），JSON
    modifications: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# === 主张与参数版本 ===

class Claim(Base, IDMixin, TimestampMixin):
    """实验主张：复核确认后生成，包含当前参数版本。新版本替代旧版本。"""
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False, index=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    # 主张内容（subject/predicate/object/conditions 等，JSON 完全由候选+复核修改决定）
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 当前参数版本：{key, value, unit, scope, version, effective_at}
    parameter_version: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 生命周期状态：current / superseded（新主张确认后旧主张被 supersede）
    status: Mapped[str] = mapped_column(String(32), default="current", nullable=False)
    # 知识验证状态：null / supported / partially_supported / refuted（结果发布为知识时填入）
    knowledge_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    replaces_claim_id: Mapped[int | None] = mapped_column(ForeignKey("claims.id"), nullable=True)


# === 任务与行动审计 ===

class Task(Base, IDMixin, TimestampMixin):
    """任务：一个会议可生成多个任务（一键修正时旧任务保留为 blocked，另建新任务草稿）。"""
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False, index=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    claim_id: Mapped[int | None] = mapped_column(ForeignKey("claims.id"), nullable=True)
    # draft / audited / running / completed / blocked / needs_confirmation
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 计划参数（来自主张版本，可由人工调整）
    planned_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 审批门：pending / approved / rejected
    approval_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 资源门：pending / ready（用户补充物料/设备/排期后标记 ready）
    resource_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    resources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 失败边界门：用户确认知晓历史失败边界风险后置 true
    failure_boundary_ack: Mapped[bool] = mapped_column(default=False, nullable=False)
    # 飞书侧任务 GUID（编排器 POST /api/v1/task/status 回写）
    feishu_task_guid: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)


class ActionAudit(Base, IDMixin, TimestampMixin):
    """行动前审计：一个任务一条审计记录。passed/blocked。"""
    __tablename__ = "action_audits"
    __table_args__ = (UniqueConstraint("task_id", name="uq_audit_per_task"),)

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    # pending / passed / blocked
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    auditor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    audited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 五项检查结果：{version_unit, evidence_scope, approval, resource, failure_boundary}
    checks: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# === 结果回流 ===

class Result(Base, IDMixin, TimestampMixin):
    __tablename__ = "results"

    result_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    submitter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # 实际参数（与计划参数对比；偏差不覆盖计划）
    actual_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    files: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # submitted / published / frozen
    status: Mapped[str] = mapped_column(String(32), default="submitted", nullable=False)
    publisher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 发布时对主张的判定：supported / partially_supported / refuted
    knowledge_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 失败边界卡：{phenomenon, trigger_condition, ruled_out, root_cause_status, next_step}
    failure_boundary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 模型偏差卡：{model_version, prediction, actual, deviation_type, feedback_task}
    model_feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# === 审计事件 ===

class AuditEvent(Base, IDMixin, TimestampMixin):
    __tablename__ = "audit_events"

    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
