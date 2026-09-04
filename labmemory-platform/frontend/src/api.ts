import type {
  AuditCompareOut,
  ControlTowerOut,
  ExperimentBrief,
  ExperimentOut,
  ExperimentPassport,
  LoginOut,
  FeishuAuthorizeOut,
  MeetingDetailOut,
  PassportSummaryOut,
  ProjectOut,
  QAAnswerOut,
  QACitation,
  QASessionDetailOut,
  QASessionOut,
  ResultOut,
  TaskOut,
  User,
  UserAdminOut,
  UserRole,
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
  // 401（非 auth 接口）：token 失效/被吊销，清登录态并回登录页，避免后续请求连环 401
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    clearToken();
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError("unauthorized", "登录已失效，请重新登录", 401);
  }
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

// === 飞书 UUAP 免登 ===
export const apiFeishuAuthorize = () =>
  request<FeishuAuthorizeOut>("/api/auth/feishu/authorize");

export const apiFeishuMockLogin = (userKey: string, displayName?: string) =>
  request<LoginOut>("/api/auth/feishu/mock-login", {
    method: "POST",
    body: JSON.stringify({ user_key: userKey, display_name: displayName }),
  });

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
export const apiAskQuestion = (
  question: string,
  sessionId?: string | null,
  sessionTitle?: string | null,
) =>
  request<QAAnswerOut>("/api/qa/ask", {
    method: "POST",
    body: JSON.stringify({
      question,
      ...(sessionId ? { session_id: sessionId } : {}),
      ...(sessionTitle ? { session_title: sessionTitle } : {}),
    }),
  });

export type QAStreamEvent =
  | { name: "session"; data: { session_id: string | null; session_title: string | null } }
  | { name: "intent"; data: { intent: "rag" | "chat"; reason: string } }
  | { name: "retrieval_started"; data: Record<string, never> }
  | {
      name: "retrieval_completed";
      data: { retrieval_details: Record<string, unknown>; citations: QACitation[] };
    }
  | { name: "answer_started"; data: Record<string, never> }
  | {
      name: "answer";
      data: {
        text: string;
        refused: boolean;
        missing_conditions?: string[];
        warning?: string | null;
      };
    }
  | {
      name: "refused";
      data: {
        reason: string;
        missing_conditions: string[];
        retrieval_details: Record<string, unknown>;
      };
    }
  | { name: "done"; data: QAAnswerOut };

/**
 * SSE 流式问答：按阶段回调 onEvent。HTTP 非 2xx 抛 ApiError。
 *
 * 用 fetch + ReadableStream 而非 EventSource，因为 EventSource 不支持 POST
 * 与 Authorization 头（需 query param 鉴权，与项目 JWT 头风格不符）。
 */
export async function apiAskQuestionStream(
  question: string,
  sessionId: string | null,
  sessionTitle: string | null,
  onEvent: (evt: QAStreamEvent) => void,
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch("/api/qa/ask/stream", {
    method: "POST",
    headers,
    body: JSON.stringify({
      question,
      ...(sessionId ? { session_id: sessionId } : {}),
      ...(sessionTitle ? { session_title: sessionTitle } : {}),
    }),
  });
  if (res.status === 401) {
    clearToken();
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError("unauthorized", "登录已失效，请重新登录", 401);
  }
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
  if (!res.body) throw new ApiError("no_stream", "响应无流式 body", res.status);

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE 事件以空行分隔
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const evt = parseSseEvent(part);
      if (evt) onEvent(evt);
    }
  }
  if (buffer.trim()) {
    const evt = parseSseEvent(buffer);
    if (evt) onEvent(evt);
  }
}

function parseSseEvent(raw: string): QAStreamEvent | null {
  let name = "";
  let dataStr = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
  }
  if (!name) return null;
  let data: unknown = {};
  if (dataStr) {
    try {
      data = JSON.parse(dataStr);
    } catch {
      data = {};
    }
  }
  return { name, data } as QAStreamEvent;
}

export const apiListQASessions = (params?: {
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
}) =>
  request<QASessionOut[]>(
    `/api/qa/sessions?${new URLSearchParams({
      ...(params?.limit ? { limit: String(params.limit) } : {}),
      ...(params?.offset ? { offset: String(params.offset) } : {}),
      ...(params?.includeArchived ? { include_archived: "true" } : {}),
    })}`,
  );

export const apiGetQASession = (id: number | string) =>
  request<QASessionDetailOut>(`/api/qa/sessions/${id}`);

export const apiPatchQASession = (
  id: number | string,
  patch: { title?: string; archived?: boolean },
) =>
  request<QASessionOut>(`/api/qa/sessions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export const apiDeleteQASession = (id: number | string) =>
  request<void>(`/api/qa/sessions/${id}`, { method: "DELETE" });

// === Admin ===
export const apiResetDemo = (mode: "clear" | "pending" | "full") =>
  request<{ status: string; mode: string; message: string }>(`/api/admin/reset-demo?mode=${mode}`, {
    method: "POST",
  });

// === 管理员用户管理 ===
export const apiListUsers = () => request<UserAdminOut[]>("/api/admin/users");

export const apiPatchUserRole = (userId: number, globalRole: UserRole) =>
  request<UserAdminOut>(`/api/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ global_role: globalRole }),
  });

export const apiAddUserMember = (userId: number, experimentId: string, role: UserRole) =>
  request<UserAdminOut>(`/api/admin/users/${userId}/members`, {
    method: "POST",
    body: JSON.stringify({ experiment_id: experimentId, role }),
  });

export const apiRemoveUserMember = (userId: number, experimentId: string) =>
  request<UserAdminOut>(`/api/admin/users/${userId}/members/${experimentId}`, {
    method: "DELETE",
  });
