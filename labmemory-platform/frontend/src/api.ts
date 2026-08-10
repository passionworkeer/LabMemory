import type {
  AuditCompareOut,
  ControlTowerOut,
  ExperimentBrief,
  ExperimentOut,
  ExperimentPassport,
  LoginOut,
  MeetingDetailOut,
  PassportSummaryOut,
  ProjectOut,
  QAAnswerOut,
  ResultOut,
  TaskOut,
  User,
} from "./types";

const TOKEN_KEY = "labmemory_token";
const USER_KEY = "labmemory_user";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string, user: User) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getStoredUser(): User | null {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) {
    let msg = res.statusText;
    let code = "http_error";
    try {
      const j = await res.json();
      msg = j.message || msg;
      code = j.code || code;
    } catch {
      // ignore
    }
    throw new ApiError(code, msg, res.status);
  }
  if (res.status === 204) return null as T;
  return res.json() as Promise<T>;
}

// === Auth ===
export const apiLogin = (username: string, password: string) =>
  request<LoginOut>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });

export const apiMe = () => request<User>("/api/auth/me");

// === Control Tower ===
export const apiControlTower = () => request<ControlTowerOut>("/api/control-tower");

// === Experiments ===
export const apiListExperiments = () => request<ExperimentOut[]>("/api/experiments");
export const apiListProjects = () => request<ProjectOut[]>("/api/projects");
export const apiCreateExperiment = (payload: {
  experiment_id: string;
  project_id: string;
  name: string;
  owner_username: string;
  parameters_template?: Record<string, unknown>;
}) =>
  request<ExperimentOut>("/api/experiments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
export const apiAddMember = (experimentId: string, username: string, role: "pi" | "lead" | "executor") =>
  request<ExperimentOut>(`/api/experiments/${experimentId}/members`, {
    method: "POST",
    body: JSON.stringify({ username, role }),
  });

// === Brief ===
export const apiGetBrief = (experimentId: string) =>
  request<ExperimentBrief>(`/api/experiments/${experimentId}/brief`);

// === Meetings ===
export const apiListMeetings = (status?: string) =>
  request<MeetingDetailOut[]>(`/api/meetings${status ? `?status=${status}` : ""}`);
export const apiGetMeeting = (meetingId: string) =>
  request<MeetingDetailOut>(`/api/meetings/${meetingId}`);
export const apiConfirmReview = (
  meetingId: string,
  payload: { decision: "confirmed" | "ended"; modifications?: Record<string, unknown>; notes?: string }
) =>
  request<MeetingDetailOut>(`/api/meetings/${meetingId}/review`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

// === Tasks ===
export const apiRunAudit = (taskId: string) =>
  request<TaskOut>(`/api/tasks/${taskId}/audit`, { method: "POST" });
export const apiStartTask = (taskId: string, assignee_username?: string) =>
  request<TaskOut>(`/api/tasks/${taskId}/start`, {
    method: "POST",
    body: JSON.stringify({ assignee_username }),
  });
export const apiAuditCompare = (taskId: string) =>
  request<AuditCompareOut>(`/api/tasks/${taskId}/audit/compare`);
export const apiAuditFix = (taskId: string) =>
  request<TaskOut>(`/api/tasks/${taskId}/audit/fix`, { method: "POST" });
export const apiApproveTask = (taskId: string, note?: string) =>
  request<TaskOut>(`/api/tasks/${taskId}/approve`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
export const apiRejectTask = (taskId: string, note?: string) =>
  request<TaskOut>(`/api/tasks/${taskId}/reject`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
export const apiUpdateResources = (
  taskId: string,
  payload: {
    materials?: { name: string; amount?: string }[];
    equipment?: { name: string; status?: string }[];
    scheduled_at?: string;
    assignee_username?: string;
    note?: string;
  }
) =>
  request<TaskOut>(`/api/tasks/${taskId}/resources`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
export const apiAckFailureBoundary = (taskId: string) =>
  request<TaskOut>(`/api/tasks/${taskId}/ack-failure-boundary`, { method: "POST" });

// === Results ===
export const apiSubmitResult = (
  taskId: string,
  payload: {
    actual_params?: Record<string, unknown>;
    metrics?: Record<string, unknown>;
    files?: unknown[];
    notes?: string;
  }
) =>
  request<ResultOut>(`/api/tasks/${taskId}/results`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
export const apiPublishResult = (
  resultId: string,
  payload: {
    knowledge_status: "supported" | "partially_supported" | "refuted";
    notes?: string;
    failure_boundary?: Record<string, unknown>;
    model_feedback?: Record<string, unknown>;
  }
) =>
  request<ResultOut>(`/api/results/${resultId}/publish`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

// === Passport ===
export const apiListPassports = () => request<PassportSummaryOut[]>("/api/passports");
export const apiGetPassport = (experimentId: string) =>
  request<ExperimentPassport>(`/api/experiments/${experimentId}/passport`);

// === QA ===
export const apiAskQuestion = (question: string) =>
  request<QAAnswerOut>("/api/qa/ask", {
    method: "POST",
    body: JSON.stringify({ question }),
  });

// === Admin ===
export const apiResetDemo = (mode: "clear" | "pending" | "full") =>
  request<{ status: string; mode: string; message: string }>(`/api/admin/reset-demo?mode=${mode}`, {
    method: "POST",
  });
