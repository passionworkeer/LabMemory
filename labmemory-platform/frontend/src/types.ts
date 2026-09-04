// 后端 API 类型定义（与 app/schemas.py 对齐）

export type UserRole = "viewer" | "executor" | "lead" | "pi" | "admin";

export interface User {
  id: number;
  username: string;
  display_name: string;
  global_role: UserRole;
  feishu_user_id?: string | null;
  source?: string;
}

export interface LoginOut {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export interface ProjectOut {
  id: number;
  project_id: string;
  name: string;
  description?: string | null;
  pi_user_id: number;
}

export interface ExperimentMemberOut {
  id: number;
  user_id: number;
  username: string;
  display_name: string;
  role: "viewer" | "executor" | "lead" | "pi";
  experiment_id?: string | null;
}

export interface ExperimentOut {
  id: number;
  experiment_id: string;
  project_id: string;
  name: string;
  status: string;
  owner_user_id: number;
  parameters_template?: Record<string, unknown> | null;
  members: ExperimentMemberOut[];
}

export interface CandidateOut {
  candidate_id: string;
  type: string;
  title: string;
  description?: string | null;
  experiment_ref?: string | null;
  parameters: { name: string; value: string; unit?: string }[];
  confidence?: number | null;
  evidence: { speaker?: string; text: string; start_offset_sec?: number; end_offset_sec?: number }[];
  status?: string | null;
  needs_review?: boolean | null;
}

export interface MeetingReviewOut {
  id: number;
  meeting_id: string;
  experiment_id: string;
  status: "pending" | "processed";
  decision?: "confirmed" | "ended" | null;
  reviewer_id?: number | null;
  reviewed_at?: string | null;
  modifications?: Record<string, unknown> | null;
  notes?: string | null;
}

export interface ClaimOut {
  id: number;
  claim_id: string;
  meeting_id: string;
  experiment_id: string;
  content: Record<string, unknown>;
  parameter_version?: {
    parameters?: { name: string; value: string; unit?: string }[];
    version?: string;
    effective_at?: string;
    scope?: Record<string, unknown>;
  } | null;
  status: string;
  knowledge_status?: string | null;
  replaces_claim_id?: number | null;
}

export interface ActionAuditOut {
  id: number;
  task_id: string;
  status: "pending" | "passed" | "blocked" | "needs_confirmation";
  auditor_id?: number | null;
  audited_at?: string | null;
  checks?: Record<string, unknown> | null;
  result?: {
    overall?: string;
    reasons?: string[];
    confirmations?: string[];
  } | null;
}

export interface TaskOut {
  id: number;
  task_id: string;
  meeting_id: string;
  experiment_id: string;
  claim_id?: number | null;
  status: "draft" | "audited" | "running" | "completed" | "blocked" | "needs_confirmation";
  assignee_id?: number | null;
  due_date?: string | null;
  planned_params?: Record<string, unknown> | null;
  approval_status?: "pending" | "approved" | "rejected";
  approved_by?: number | null;
  approved_at?: string | null;
  approval_note?: string | null;
  resource_status?: "pending" | "ready";
  resources?: Record<string, unknown> | null;
  failure_boundary_ack?: boolean;
}

export interface ResultOut {
  id: number;
  result_id: string;
  task_id: string;
  submitter_id: number;
  actual_params?: Record<string, unknown> | null;
  metrics?: Record<string, unknown> | null;
  files?: unknown[] | null;
  status: "submitted" | "published" | "frozen";
  publisher_id?: number | null;
  published_at?: string | null;
  knowledge_status?: "supported" | "partially_supported" | "refuted" | null;
  failure_boundary?: {
    phenomenon?: string;
    trigger_condition?: string;
    ruled_out?: string;
    root_cause_status?: string;
    next_step?: string;
  } | null;
  model_feedback?: {
    model_version?: string;
    prediction?: string;
    actual?: string;
    deviation_type?: string;
    feedback_task?: string;
  } | null;
  notes?: string | null;
  planned_params?: Record<string, unknown> | null;
}

export interface MeetingChainItem {
  meeting_id: string;
  experiment_id: string;
  title: string;
  captured_at?: string | null;
  review?: MeetingReviewOut | null;
  claim?: ClaimOut | null;
  task?: TaskOut | null;
  audit?: ActionAuditOut | null;
  results: ResultOut[];
  candidates: CandidateOut[];
  transcript: { speaker: string; text: string; start_offset_sec?: number; end_offset_sec?: number }[];
  summary?: string | null;
}

export interface MeetingDetailOut extends MeetingChainItem {
  experiment_id: string;
  source: string;
  source_url?: string | null;
  organizer?: string | null;
  participants: string[];
  risks: unknown[];
  action_items: unknown[];
  open_questions: unknown[];
}

export interface TimelineEvent {
  timestamp: string;
  event_type: string;
  actor_id?: number | null;
  target_type: string;
  target_id: string;
  summary: string;
  details?: Record<string, unknown> | null;
}

export interface ExperimentPassport {
  experiment_id: string;
  project_id: string;
  name: string;
  status: string;
  current_claim?: ClaimOut | null;
  meetings: MeetingChainItem[];
  timeline: TimelineEvent[];
}

export interface PassportClaimSummary {
  claim_id: string;
  status: string;
  knowledge_status?: string | null;
  parameter_version?: Record<string, unknown> | null;
}

export interface PassportSummaryOut {
  experiment_id: string;
  project_id: string;
  name: string;
  status: string;
  owner_display_name: string;
  members: ExperimentMemberOut[];
  meeting_count: number;
  pending_review_count: number;
  current_claim?: PassportClaimSummary | null;
  task_count: number;
  blocked_task_count: number;
  published_result_count: number;
  last_activity_at?: string | null;
}

export interface ControlTowerOut {
  pending_reviews: number;
  blocked_tasks: number;
  anomalies: number;
  published_24h: number;
  active_experiments: number;
  need_attention: {
    type: string;
    target_id: string;
    experiment_id: string;
    title: string;
    status: string;
    severity: string;
  }[];
}

export interface ExperimentBrief {
  experiment_id: string;
  project_id: string;
  name: string;
  status: string;
  current_goal?: string | null;
  current_claim?: ClaimOut | null;
  last_result?: ResultOut | null;
  failure_boundaries: Record<string, unknown>[];
  resources: Record<string, unknown>;
  pending_questions: string[];
}

export interface AuditCompareOut {
  task_id: string;
  meeting_id: string;
  experiment_id: string;
  old_claim?: ClaimOut | null;
  current_claim?: ClaimOut | null;
  is_blocked: boolean;
  affected_objects: Record<string, number>;
  recommended_action?: string | null;
  task?: TaskOut | null;
  audit?: ActionAuditOut | null;
}

export interface QACitation {
  ref: string;
  type: "claim" | "result" | "evidence" | "failure_boundary";
  ref_id: string;
  title: string;
  knowledge_status?: string | null;
  url?: string | null;
  metadata?: Record<string, unknown>;
}

export interface QARetrievalDetails {
  permission_filtered_experiments?: number;
  status_filtered_chunks?: number;
  bm25_hits?: number;
  vector_hits?: number;
  after_relation_expansion?: number;
  after_rerank?: number;
  top_score?: number;
  score_breakdown?: Record<string, number>;
  elapsed_sec?: number;
  /** 实际用于 BM25/向量召回的查询（经查询改写可能与原始问题不同） */
  search_query?: string;
  /** 意图门控命中时为 true：本轮直答，未执行任何检索阶段 */
  retrieval_skipped?: boolean;
  /** 门控识别的意图：greeting / thanks / goodbye / meta */
  intent?: string;
}

export interface QAModelInfo {
  embedding_mode?: string;
  embedding_model?: string;
  chat_mode?: string;
  chat_model?: string;
  top_k?: number;
  intent?: string;
}

export interface QAAnswerOut {
  question: string;
  answer: string;
  citations: QACitation[];
  retrieval_scope: Record<string, unknown>;
  retrieval_details?: QARetrievalDetails;
  model_info?: QAModelInfo;
  missing_conditions?: string[];
  refused: boolean;
  session_id?: string | null;
  session_title?: string | null;
  message_id?: number | null;
}

export interface QAMessageOut {
  id: number;
  role: "user" | "assistant";
  content: string;
  citations?: QACitation[] | null;
  refused?: boolean;
  retrieval_details?: QARetrievalDetails | null;
  model_info?: QAModelInfo | null;
  missing_conditions?: string[] | null;
  intent?: string | null;
  created_at: string;
}

export interface QASessionOut {
  id: number;
  title: string;
  archived: boolean;
  last_message_at?: string | null;
  message_count: number;
  created_at: string;
}

export interface QASessionDetailOut extends QASessionOut {
  summary?: string | null;
  summary_cursor?: number | null;
  messages: QAMessageOut[];
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface FeishuAuthorizeOut {
  mode: "mock" | "real";
  authorize_url?: string | null;
  mock_enabled: boolean;
  password_login_enabled: boolean;
}

export interface UserAdminOut {
  id: number;
  username: string;
  display_name: string;
  global_role: UserRole;
  source: string;
  feishu_user_id?: string | null;
  created_at: string;
  experiment_count: number;
  members: ExperimentMemberOut[];
}
