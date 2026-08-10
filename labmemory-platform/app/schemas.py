"""Pydantic schemas（请求/响应）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# === Auth ===

class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    global_role: str
    feishu_user_id: str | None = None


class LoginOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# === Experiment management (PI only) ===

class ExperimentMemberIn(BaseModel):
    username: str
    role: Literal["pi", "lead", "executor"]


class ExperimentMemberOut(BaseModel):
    id: int
    user_id: int
    username: str
    display_name: str
    role: str

    class Config:
        from_attributes = True


class ExperimentIn(BaseModel):
    experiment_id: str = Field(..., description="实验编号，跨数据链路唯一跟踪")
    project_id: str
    name: str
    owner_username: str
    parameters_template: dict[str, Any] | None = None


class ExperimentOut(BaseModel):
    id: int
    experiment_id: str
    project_id: str
    name: str
    status: str
    owner_user_id: int
    parameters_template: dict | None = None
    members: list[ExperimentMemberOut] = []

    class Config:
        from_attributes = True


class ProjectOut(BaseModel):
    id: int
    project_id: str
    name: str
    description: str | None = None
    pi_user_id: int


# === Meeting intake ===

class MeetingPackageIn(BaseModel):
    """对接 feishu-orchestrator 的 MeetingPackage 契约。"""
    schema_version: str = "1.0.0"
    source: str = "feishu_minutes"
    source_object_id: str
    meeting_id: str
    title: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    organizer: str | None = None
    participants: list[str] = []
    content: dict
    source_url: str | None = None
    captured_at: datetime
    metadata: dict = {}


class CandidatePackageIn(BaseModel):
    """对接 feishu-orchestrator 的 CandidatePackage 契约。"""
    schema_version: str = "1.0.0"
    source_package_id: str
    aily_skill_version: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    input_hash: str | None = None
    candidates: list[dict] = []
    risks: list = []
    action_items: list = []
    open_questions: list = []
    compiled_at: datetime | None = None
    raw_output: str | None = None


# === Meeting review ===

class ReviewConfirmIn(BaseModel):
    # confirmed=直接确认或修改后确认；ended=结束，不进入数据链路
    decision: Literal["confirmed", "ended"]
    # 修改后的参数或其他内容（用于生成主张）
    modifications: dict[str, Any] | None = None
    notes: str | None = None


class MeetingReviewOut(BaseModel):
    id: int
    meeting_id: str
    experiment_id: str
    status: str
    decision: str | None = None
    reviewer_id: int | None = None
    reviewed_at: datetime | None = None
    modifications: dict | None = None
    notes: str | None = None


# === Action audit ===

class ActionAuditOut(BaseModel):
    id: int
    task_id: str
    status: str  # pending / passed / blocked / needs_confirmation
    auditor_id: int | None = None
    audited_at: datetime | None = None
    checks: dict | None = None
    result: dict | None = None


# === Task ===

class TaskOut(BaseModel):
    id: int
    task_id: str
    meeting_id: str
    experiment_id: str
    claim_id: int | None = None
    status: str  # draft / audited / running / completed / blocked / needs_confirmation
    assignee_id: int | None = None
    due_date: datetime | None = None
    planned_params: dict | None = None
    approval_status: str = "pending"  # pending / approved / rejected
    approved_by: int | None = None
    approved_at: datetime | None = None
    approval_note: str | None = None
    resource_status: str = "pending"  # pending / ready
    resources: dict | None = None
    failure_boundary_ack: bool = False


class TaskStartIn(BaseModel):
    assignee_username: str | None = None
    due_date: datetime | None = None


class TaskApproveIn(BaseModel):
    note: str | None = None


class TaskResourcesIn(BaseModel):
    """资源补充：物料/设备/排期/备注。提交即标记 resource_status=ready。"""
    materials: list[dict] = []
    equipment: list[dict] = []
    scheduled_at: datetime | None = None
    assignee_username: str | None = None
    note: str | None = None


# === Result ===

class ResultSubmitIn(BaseModel):
    actual_params: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    files: list[dict] | None = None
    notes: str | None = None


class ResultPublishIn(BaseModel):
    knowledge_status: Literal["supported", "partially_supported", "refuted"]
    notes: str | None = None
    failure_boundary: dict[str, Any] | None = None
    model_feedback: dict[str, Any] | None = None


class ResultOut(BaseModel):
    id: int
    result_id: str
    task_id: str
    submitter_id: int
    actual_params: dict | None = None
    metrics: dict | None = None
    files: list | None = None
    status: str
    publisher_id: int | None = None
    published_at: datetime | None = None
    knowledge_status: str | None = None
    failure_boundary: dict | None = None
    model_feedback: dict | None = None
    notes: str | None = None
    planned_params: dict | None = None


# === Control Tower ===

class ControlTowerOut(BaseModel):
    pending_reviews: int
    blocked_tasks: int
    anomalies: int
    published_24h: int
    active_experiments: int
    need_attention: list[dict] = []


# === Pre-meeting Brief ===

class ExperimentBrief(BaseModel):
    experiment_id: str
    project_id: str
    name: str
    status: str
    current_goal: str | None = None
    current_claim: ClaimOut | None = None
    last_result: ResultOut | None = None
    failure_boundaries: list[dict] = []
    resources: dict = {}
    pending_questions: list[str] = []


# === Action Audit Compare ===

class AuditCompareOut(BaseModel):
    task_id: str
    meeting_id: str
    experiment_id: str
    old_claim: ClaimOut | None = None
    current_claim: ClaimOut | None = None
    is_blocked: bool
    affected_objects: dict = {}
    recommended_action: str | None = None
    task: TaskOut | None = None
    audit: ActionAuditOut | None = None


# === Trusted QA ===

class QAAskIn(BaseModel):
    question: str


class QAAnswerOut(BaseModel):
    question: str
    answer: str
    citations: list[dict] = []
    retrieval_scope: dict = {}
    refused: bool = False


# === Audit Event (timeline) ===

class AuditEventOut(BaseModel):
    id: int
    actor_id: int | None = None
    action: str
    target_type: str
    target_id: str
    before: dict | None = None
    after: dict | None = None
    reason: str | None = None
    created_at: datetime


class CandidateOut(BaseModel):
    """Aily 候选对象（来自 CandidatePackage.candidates）。"""
    candidate_id: str
    type: str
    title: str
    description: str | None = None
    experiment_ref: str | None = None
    parameters: list[dict] = []
    confidence: float | None = None
    evidence: list[dict] = []
    status: str | None = None
    needs_review: bool | None = None


class MeetingDetailOut(BaseModel):
    """会议详情：含逐字稿 + 候选对象 + 复核 + 主张 + 任务 + 审计 + 结果。"""
    meeting_id: str
    experiment_id: str
    title: str
    source: str
    source_url: str | None = None
    organizer: str | None = None
    participants: list[str] = []
    summary: str | None = None
    transcript: list[dict] = []
    captured_at: datetime | None = None
    candidates: list[CandidateOut] = []
    risks: list = []
    action_items: list = []
    open_questions: list = []
    review: MeetingReviewOut | None = None
    claim: ClaimOut | None = None
    task: TaskOut | None = None
    audit: ActionAuditOut | None = None
    results: list[ResultOut] = []


# === Claim ===

class ClaimOut(BaseModel):
    id: int
    claim_id: str
    meeting_id: str
    experiment_id: str
    content: dict
    parameter_version: dict | None = None
    status: str
    knowledge_status: str | None = None
    replaces_claim_id: int | None = None


# === Passport ===

class MeetingChainItem(BaseModel):
    """单次会议的完整数据链：复核 -> 主张 -> 任务 -> 审计 -> 结果。"""
    meeting_id: str
    experiment_id: str = ""
    title: str
    captured_at: datetime | None = None
    review: MeetingReviewOut | None = None
    claim: ClaimOut | None = None
    task: TaskOut | None = None
    audit: ActionAuditOut | None = None
    results: list[ResultOut] = []
    candidates: list[CandidateOut] = []
    transcript: list[dict] = []
    summary: str | None = None


class TimelineEvent(BaseModel):
    """实验统一时间线事件。"""
    timestamp: datetime
    event_type: str
    actor_id: int | None = None
    target_type: str
    target_id: str
    summary: str
    details: dict | None = None


class ExperimentPassport(BaseModel):
    experiment_id: str
    project_id: str
    name: str
    status: str
    current_claim: ClaimOut | None = None
    # 数据关系链：按会议 ID 组织（一个实验多个会议）
    meetings: list[MeetingChainItem] = []
    # 统一时间线：按实验 ID 组织，按时间排序
    timeline: list[TimelineEvent] = []


class PassportClaimSummary(BaseModel):
    """护照列表中的当前主张摘要（轻量版 ClaimOut）。"""
    claim_id: str
    status: str
    knowledge_status: str | None = None
    parameter_version: dict | None = None


class PassportSummaryOut(BaseModel):
    """实验护照列表项：实验基本信息 + 数据链概览统计。"""
    experiment_id: str
    project_id: str
    name: str
    status: str
    owner_display_name: str
    members: list[ExperimentMemberOut] = []
    meeting_count: int = 0
    pending_review_count: int = 0
    current_claim: PassportClaimSummary | None = None
    task_count: int = 0
    blocked_task_count: int = 0
    published_result_count: int = 0
    last_activity_at: datetime | None = None
