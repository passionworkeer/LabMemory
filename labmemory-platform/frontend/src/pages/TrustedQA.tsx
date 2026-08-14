import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  apiAskQuestionStream,
  apiDeleteQASession,
  apiGetQASession,
  apiListQASessions,
  apiPatchQASession,
  type QAStreamEvent,
} from "../api";
import type {
  QAAnswerOut,
  QACitation,
  QAMessageOut,
  QASessionOut,
} from "../types";
import { useAuth } from "../store";

interface Msg {
  _id: number | string;  // 唯一标识：live 消息用随机数，历史消息用 backend id
  role: "user" | "ai";
  text: string;
  citations?: QACitation[];
  refused?: boolean;
  retrievalDetails?: QAAnswerOut["retrieval_details"];
  modelInfo?: QAAnswerOut["model_info"];
  missingConditions?: string[];
  warning?: string | null;
  streamed?: boolean;
  ts: number;
}

function messageToMsg(m: QAMessageOut): Msg {
  return {
    _id: m.id,
    role: m.role === "user" ? "user" : "ai",
    text: m.content,
    citations: m.citations ?? undefined,
    refused: m.refused ?? undefined,
    retrievalDetails: m.retrieval_details ?? undefined,
    modelInfo: m.model_info ?? undefined,
    missingConditions: m.missing_conditions ?? undefined,
    ts: new Date(m.created_at).getTime(),
  };
}

const ROLE_LABEL: Record<string, string> = {
  pi: "项目负责人",
  lead: "实验负责人",
  executor: "执行人",
  admin: "管理员",
};

const CITATION_ICON: Record<QACitation["type"], string> = {
  claim: "📝",
  result: "📊",
  evidence: "💬",
  failure_boundary: "⚠️",
};

const CITATION_LABEL: Record<QACitation["type"], string> = {
  claim: "主张",
  result: "结果",
  evidence: "证据",
  failure_boundary: "失败边界",
};

const CITATION_COLOR: Record<QACitation["type"], string> = {
  claim: "#3370ff",
  result: "#16a46f",
  evidence: "#7357d8",
  failure_boundary: "#d98b00",
};

const KNOWLEDGE_TAG: Record<string, { label: string; cls: string }> = {
  supported: { label: "已验证·支持", cls: "green" },
  partially_supported: { label: "已验证·部分支持", cls: "amber" },
  refuted: { label: "已验证·推翻", cls: "red" },
};

const STAGE_ICONS = ["🔑", "📊", "🔍", "🧠", "🔗", "⚡"];

const INTENT_LABEL: Record<string, string> = {
  greeting: "寒暄问候",
  thanks: "致谢",
  goodbye: "告别",
  meta: "能力询问",
};

export default function TrustedQA() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState<"thinking" | "retrieving">("thinking");
  // 内容已开始流式渲染（answer 事件或拒答路径的 done 事件触发）。
  // 一旦为 true，下方打字机指示器立即隐藏，避免 _maybe_summarize LLM 调用期间
  // 在已完成的 AI 消息下方残留"思考中..."气泡。loading 仍保持 true 以禁用输入框。
  const [answerStreaming, setAnswerStreaming] = useState(false);
  const [lastScope, setLastScope] = useState<QAAnswerOut | null>(null);
  const [sessions, setSessions] = useState<QASessionOut[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryCursor, setSummaryCursor] = useState<number | null>(null);
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const scrollRef = useRef<HTMLDivElement>(null);
  const typingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  // ask 周期 epoch：用于忽略旧 ask 的过期 SSE 事件与 finally 状态覆盖。
  // 当用户在新 ask 的 _maybe_summarize 期间提交下一问题时，旧 ask 的 done 事件
  // 与 finally 不应再覆盖新 ask 的 loading/phase/answerStreaming 状态。
  const askEpochRef = useRef(0);

  const refreshSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const list = await apiListQASessions({ limit: 50 });
      setSessions(list);
    } catch {
      /* 静默：未登录时由路由守卫处理 */
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const loadSession = useCallback(async (id: string) => {
    try {
      const detail = await apiGetQASession(id);
      setSessionId(String(detail.id));
      setMessages(detail.messages.map(messageToMsg));
      setSummary(detail.summary ?? null);
      setSummaryCursor(detail.summary_cursor ?? null);
      const lastAi = [...detail.messages].reverse().find((m) => m.role === "assistant");
      if (lastAi) {
        setLastScope({
          question: "",
          answer: lastAi.content,
          citations: lastAi.citations ?? [],
          retrieval_scope: {},
          retrieval_details: lastAi.retrieval_details ?? undefined,
          model_info: lastAi.model_info ?? undefined,
          missing_conditions: lastAi.missing_conditions ?? [],
          refused: lastAi.refused ?? false,
        } as QAAnswerOut);
      } else {
        setLastScope(null);
      }
    } catch {
      /* 会话不存在或越权：静默忽略，留在新建态 */
    }
  }, []);

  useEffect(() => {
    refreshSessions();
    const sid = searchParams.get("s");
    if (sid) {
      loadSession(sid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    return () => {
      if (typingTimer.current) clearInterval(typingTimer.current);
    };
  }, []);

  const streamAnswer = (
    fullText: string,
    citations: QACitation[],
    refused: boolean,
    rd: QAAnswerOut["retrieval_details"],
    mi: QAAnswerOut["model_info"],
    mc: string[] | undefined,
    warning: string | null,
    epoch: number,
  ) => {
    // 每条 AI 消息分配唯一 id，用于 setInterval 定位消息（支持并发 ask 各自更新自己的消息）
    const msgId = Date.now() + Math.random();
    setMessages((prev) => {
      // 严格模式下 setMessages updater 会被调用两次；用 msgId 去重避免重复添加
      if (prev.some((m) => m._id === msgId)) return prev;
      const aiMsg: Msg = {
        _id: msgId,
        role: "ai",
        text: "",
        citations,
        refused,
        retrievalDetails: rd,
        modelInfo: mi,
        missingConditions: mc,
        warning,
        streamed: true,
        ts: Date.now(),
      };
      return [...prev, aiMsg];
    });

    if (typingTimer.current) clearInterval(typingTimer.current);
    let i = 0;
    typingTimer.current = setInterval(() => {
      i += 2;
      const slice = fullText.slice(0, i);
      setMessages((curr) => {
        const idx = curr.findIndex((m) => m._id === msgId);
        if (idx === -1) return curr;  // 消息已不存在（清空会话），停止更新
        const arr = [...curr];
        arr[idx] = { ...arr[idx], text: slice, streamed: i < fullText.length };
        return arr;
      });
      if (i >= fullText.length && typingTimer.current) {
        clearInterval(typingTimer.current);
        typingTimer.current = null;
        // 打字机跑完：AI 回复已完整呈现，立即启用输入框。
        // epoch 检查避免覆盖更新的 ask 的 loading 状态。
        if (epoch === askEpochRef.current) {
          setLoading(false);
        }
      }
    }, 12);
  };

  const ask = async (q?: string) => {
    const text = (q ?? question).trim();
    if (!text || loading) return;
    const myEpoch = ++askEpochRef.current;
    setQuestion("");
    setMessages((prev) => [
      ...prev,
      { _id: Date.now() + Math.random(), role: "user", text, ts: Date.now() },
    ]);
    setLoading(true);
    setPhase("thinking");
    setAnswerStreaming(false);

    // SSE 事件处理期间累积的中间状态；done 事件到达后构造完整 QAAnswerOut
    let streamedAnswer: {
      text: string;
      refused: boolean;
      missingConditions?: string[];
      warning?: string | null;
      citations: QACitation[];
      retrievalDetails?: QAAnswerOut["retrieval_details"];
      modelInfo?: QAAnswerOut["model_info"];
    } | null = null;

    try {
      await apiAskQuestionStream(text, sessionId ?? null, null, (evt: QAStreamEvent) => {
        // 旧 ask 的过期事件：忽略，避免覆盖新 ask 的状态
        if (myEpoch !== askEpochRef.current) return;
        switch (evt.name) {
          case "session": {
            const sid = evt.data.session_id;
            if (sid && sid !== sessionId) {
              setSessionId(sid);
              setSearchParams({ s: sid }, { replace: true });
            }
            break;
          }
          case "intent":
            // rag → 切换"检索中..."；chat → 保持"思考中..."
            setPhase(evt.data.intent === "rag" ? "retrieving" : "thinking");
            break;
          case "retrieval_started":
            setPhase("retrieving");
            break;
          case "retrieval_completed":
            // 检索完成，进入回答 LLM 阶段
            setPhase("thinking");
            streamedAnswer = {
              text: "",
              refused: false,
              citations: evt.data.citations ?? [],
              retrievalDetails: evt.data.retrieval_details as
                | QAAnswerOut["retrieval_details"]
                | undefined,
            };
            break;
          case "answer_started":
            setPhase("thinking");
            break;
          case "answer":
            if (streamedAnswer) {
              streamedAnswer.text = evt.data.text;
              streamedAnswer.refused = evt.data.refused;
              streamedAnswer.missingConditions = evt.data.missing_conditions;
              streamedAnswer.warning = evt.data.warning ?? null;
            } else {
              // chat 路径无 retrieval_completed，先初始化
              streamedAnswer = {
                text: evt.data.text,
                refused: evt.data.refused,
                missingConditions: evt.data.missing_conditions,
                warning: evt.data.warning ?? null,
                citations: [],
              };
            }
            // 内容开始流式：立即隐藏下方打字机指示器，避免 _maybe_summarize
            // LLM 调用期间在已完成的 AI 消息下方残留"思考中..."气泡
            setAnswerStreaming(true);
            // 启动打字机渲染（done 事件到达后再补全 session_id/message_id）
            streamAnswer(
              evt.data.text,
              streamedAnswer.citations,
              evt.data.refused,
              streamedAnswer.retrievalDetails,
              undefined,
              evt.data.missing_conditions,
              evt.data.warning ?? null,
              myEpoch,
            );
            break;
          case "refused":
            // rag 早期拒答（检索阶段），无 answer 事件
            streamedAnswer = {
              text: "",
              refused: true,
              missingConditions: evt.data.missing_conditions,
              citations: [],
              retrievalDetails: evt.data.retrieval_details as
                | QAAnswerOut["retrieval_details"]
                | undefined,
            };
            break;
          case "done": {
            // done.data 是完整 QAAnswerOut；以此为最终权威
            const r = evt.data as QAAnswerOut;
            setLastScope(r);
            if (r.session_id && r.session_id !== sessionId) {
              setSessionId(r.session_id);
              setSearchParams({ s: r.session_id }, { replace: true });
            }
            // 若已 streamAnswer 过（answer 事件触发），用 done 的权威字段补全
            // lastScope；否则（早期拒答）现在才渲染
            if (!streamedAnswer || !streamedAnswer.text) {
              setAnswerStreaming(true);
              streamAnswer(
                r.answer,
                r.citations,
                r.refused,
                r.retrieval_details,
                r.model_info,
                r.missing_conditions,
                (r.retrieval_scope.warning as string | null) ?? null,
                myEpoch,
              );
            } else {
              // 已渲染：仅刷新 lastScope 中的 model_info 等字段（在 streamAnswer 时未填）
              setLastScope(r);
            }
            refreshSessions();
            break;
          }
        }
      });
    } catch (e) {
      if (myEpoch !== askEpochRef.current) return;
      setMessages((prev) => [
        ...prev,
        {
          _id: Date.now() + Math.random(),
          role: "ai",
          text: `查询失败：${(e as Error).message}`,
          refused: true,
          ts: Date.now(),
        },
      ]);
    } finally {
      // 仅当本 ask 仍是最新时才重置状态；否则新 ask 已接管，旧 ask 不应覆盖
      if (myEpoch === askEpochRef.current) {
        setLoading(false);
        setPhase("thinking");
        setAnswerStreaming(false);
      }
    }
  };

  const newSession = () => {
    if (typingTimer.current) {
      clearInterval(typingTimer.current);
      typingTimer.current = null;
    }
    setSessionId(null);
    setMessages([]);
    setLastScope(null);
    setSummary(null);
    setSummaryCursor(null);
    setSearchParams({}, { replace: true });
  };

  const selectSession = async (id: number) => {
    if (typingTimer.current) {
      clearInterval(typingTimer.current);
      typingTimer.current = null;
    }
    const sid = String(id);
    setSessionId(sid);
    setSearchParams({ s: sid }, { replace: true });
    await loadSession(sid);
  };

  const renameSession = async (id: number, oldTitle: string) => {
    const title = window.prompt("重命名会话", oldTitle);
    if (!title || !title.trim() || title === oldTitle) return;
    try {
      await apiPatchQASession(id, { title: title.trim() });
      await refreshSessions();
    } catch (e) {
      window.alert(`重命名失败：${(e as Error).message}`);
    }
  };

  const deleteSession = async (id: number) => {
    if (!window.confirm("删除该会话？所有问答历史将一并删除，且不可恢复。")) return;
    try {
      await apiDeleteQASession(id);
      if (sessionId === String(id)) newSession();
      await refreshSessions();
    } catch (e) {
      window.alert(`删除失败：${(e as Error).message}`);
    }
  };

  const suggestions = lastScope?.citations?.length
    ? Array.from(new Set(lastScope.citations.map((c) => c.metadata?.experiment_id as string).filter(Boolean)))
        .slice(0, 1)
        .map((eid) => [
          { q: `${eid} 当前参数版本是什么？`, label: `${eid} · 当前参数版本` },
          { q: `${eid} 有哪些已验证结果？`, label: `${eid} · 已验证结果` },
          { q: `${eid} 有哪些失败边界？`, label: `${eid} · 失败边界` },
        ])
        .flat()
    : [
        { q: "EXP-DEMO-001 当前推荐温度是多少？", label: "EXP-DEMO-001 · 当前推荐温度" },
        { q: "有哪些失败边界需要注意？", label: "失败边界总览" },
        { q: "催化剂 0.8 eq 是否验证？", label: "催化剂用量 · 验证状态" },
      ];

  // 直答轮（retrieval_skipped）不判定降级——未执行检索，模板直答属正常路径
  const isDegraded =
    !lastScope?.retrieval_details?.retrieval_skipped &&
    !!lastScope?.model_info &&
    (lastScope.model_info.embedding_mode === "hash-fallback" ||
      lastScope.model_info.chat_mode === "template-fallback");

  return (
    <div className="fade-in">
      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: "248px minmax(0, 1fr) 340px" }}
      >
        {/* 左侧会话列表 */}
        <div className="card flex flex-col" style={{ height: 680, padding: 0, overflow: "hidden" }}>
          <div
            className="flex items-center justify-between"
            style={{
              padding: "12px 14px",
              borderBottom: "1px solid var(--line-light)",
              background: "linear-gradient(180deg, rgba(250,252,255,0.85) 0%, rgba(255,255,255,0.4) 100%)",
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>
              会话历史
            </span>
            <button
              className="btn sm ghost"
              onClick={newSession}
              style={{ fontSize: 12, padding: "2px 8px" }}
              aria-label="新建会话"
              title="新建会话"
            >
              + 新建
            </button>
          </div>
          <div className="flex-1 overflow-auto" style={{ minHeight: 0 }}>
            {sessionsLoading && sessions.length === 0 && (
              <div style={{ padding: "16px", fontSize: 12, color: "var(--muted)" }}>加载中...</div>
            )}
            {!sessionsLoading && sessions.length === 0 && (
              <div style={{ padding: "16px", fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
                暂无历史会话。提一个问题即可自动创建。
              </div>
            )}
            {sessions.map((s) => {
              const active = sessionId === String(s.id);
              return (
                <div
                  key={s.id}
                  onClick={() => selectSession(s.id)}
                  className="qa-session-row"
                  style={{
                    padding: "10px 12px",
                    cursor: "pointer",
                    borderBottom: "1px solid var(--line-light)",
                    background: active ? "var(--blue-soft)" : "transparent",
                    borderLeft: active ? "3px solid var(--blue)" : "3px solid transparent",
                    transition: "background 0.12s",
                  }}
                >
                  <div
                    style={{
                      fontSize: 12.5,
                      fontWeight: 600,
                      color: "var(--text)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      marginBottom: 3,
                    }}
                    title={s.title}
                  >
                    {s.title || "新会话"}
                  </div>
                  <div
                    className="flex items-center justify-between"
                    style={{ fontSize: 10.5, color: "var(--muted)" }}
                  >
                    <span>
                      {s.message_count > 0 ? `${s.message_count} 条` : "空"} ·{" "}
                      {s.last_message_at
                        ? new Date(s.last_message_at).toLocaleString("zh-CN", {
                            month: "2-digit",
                            day: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : "—"}
                    </span>
                    <span style={{ display: "flex", gap: 4 }} onClick={(e) => e.stopPropagation()}>
                      <button
                        className="btn sm ghost"
                        style={{ fontSize: 10, padding: "1px 6px" }}
                        title="重命名"
                        onClick={() => renameSession(s.id, s.title)}
                      >
                        ✎
                      </button>
                      <button
                        className="btn sm ghost"
                        style={{ fontSize: 10, padding: "1px 6px", color: "var(--red)" }}
                        title="删除"
                        onClick={() => deleteSession(s.id)}
                      >
                        ✕
                      </button>
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 对话区 */}
        <div
          className="card flex flex-col"
          style={{ height: 680, padding: 0, overflow: "hidden" }}
        >
          {/* 对话头部 */}
          <div
            className="flex items-center justify-between"
            style={{
              padding: "14px 20px",
              borderBottom: "1px solid var(--line-light)",
              background: "linear-gradient(180deg, rgba(250,252,255,0.85) 0%, rgba(255,255,255,0.4) 100%)",
            }}
          >
            <div className="flex items-center gap-2.5">
              <div className="ai-avatar" style={{ width: 36, height: 36 }}>
                <SparkleIcon size={20} />
              </div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>
                  可信知识问答
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)" }}>
                  {sessionId
                    ? `会话 #${sessionId}${lastScope?.session_title ? ` · ${lastScope.session_title}` : ""}`
                    : "新会话（首次提问后自动保存）"}
                </div>
              </div>
            </div>
            {messages.length > 0 && (
              <button
                className="btn sm ghost"
                onClick={newSession}
                style={{ fontSize: 12 }}
                title="结束当前会话并新建"
              >
                新建会话
              </button>
            )}
          </div>

          {/* 消息列表 */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-auto"
            style={{ padding: "20px 22px", minHeight: 0 }}
          >
            {messages.length === 0 && !loading && (
              <div
                className="flex flex-col items-center justify-center text-center"
                style={{ height: "100%", color: "var(--muted)" }}
              >
                <div
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: 22,
                    background: "var(--blue-soft)",
                    display: "grid",
                    placeItems: "center",
                    fontSize: 34,
                    marginBottom: 16,
                  }}
                >
                  💬
                </div>
                <div
                  style={{
                    fontSize: 16,
                    fontWeight: 700,
                    color: "var(--text)",
                    marginBottom: 6,
                  }}
                >
                  向可信知识库提问
                </div>
                <div style={{ fontSize: 13, maxWidth: 420, lineHeight: 1.7 }}>
                  系统会基于实验主张、已验证结果、会议证据与失败边界做混合检索，
                  并由大模型归纳带出处的答案；若证据不足则明确拒答。
                </div>
              </div>
            )}

            {summary && (
              <div
                style={{
                  margin: "0 0 14px",
                  padding: "10px 14px",
                  background: "var(--bg)",
                  border: "1px dashed var(--line)",
                  borderRadius: 10,
                  fontSize: 12.5,
                  color: "var(--muted)",
                }}
              >
                <div
                  className="flex items-center justify-between"
                  style={{ marginBottom: summaryExpanded ? 6 : 0 }}
                  onClick={() => setSummaryExpanded((v) => !v)}
                >
                  <span style={{ fontWeight: 600, color: "var(--text)" }}>
                    📜 已折叠早期对话（至第 {summaryCursor ?? 0} 条消息）
                  </span>
                  <span style={{ fontSize: 11, cursor: "pointer" }}>
                    {summaryExpanded ? "收起" : "展开摘要"}
                  </span>
                </div>
                {summaryExpanded && (
                  <div style={{ marginTop: 6, lineHeight: 1.65, color: "var(--text)" }}>
                    {summary}
                  </div>
                )}
              </div>
            )}

            {messages.map((m) => (
              <MessageBubble key={m._id} m={m} navigate={navigate} />
            ))}

            {loading && !answerStreaming && (
              <div
                className="flex items-start gap-2.5"
                style={{ margin: "14px 0" }}
              >
                <div className="ai-avatar">
                  <SparkleIcon size={18} />
                </div>
                <div
                  className="flex items-center gap-1.5"
                  style={{
                    background: "var(--bg)",
                    border: "1px solid var(--line-light)",
                    borderRadius: 14,
                    borderBottomLeftRadius: 4,
                    padding: "10px 14px",
                  }}
                >
                  <span className="typing-dot" style={{ animationDelay: "0ms" }} />
                  <span className="typing-dot" style={{ animationDelay: "150ms" }} />
                  <span className="typing-dot" style={{ animationDelay: "300ms" }} />
                  <span style={{ fontSize: 12.5, color: "var(--muted)", marginLeft: 4 }}>
                    {phase === "retrieving" ? "检索中..." : "思考中..."}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* 输入区 */}
          <div
            className="flex gap-2 items-end"
            style={{
              padding: "14px 20px 18px",
              borderTop: "1px solid var(--line-light)",
              background: "rgba(250,252,255,0.72)",
            }}
          >
            <input
              className="input"
              style={{ fontSize: 14 }}
              placeholder="输入问题，例如：EXP-DEMO-001 当前参数版本？"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              disabled={loading}
            />
            <button
              className="send-btn"
              onClick={() => ask()}
              disabled={loading || !question.trim()}
              aria-label="发送"
            >
              <SendIcon size={18} />
            </button>
          </div>
        </div>

        {/* 右侧面板 */}
        <div className="flex flex-col gap-4">
          {/* 检索范围 */}
          <div className="card">
            <div className="section-title">
              <b>本次检索范围</b>
            </div>
            <div className="text-xs space-y-2 leading-relaxed">
              <div className="flex items-center gap-2">
                <span className="text-muted" style={{ width: 44 }}>身份</span>
                <span style={{ fontWeight: 600 }}>{user?.display_name}</span>
                {user && (
                  <span className="tag blue" style={{ fontSize: 10.5, padding: "1px 7px" }}>
                    {ROLE_LABEL[user.global_role] || user.global_role}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted" style={{ width: 44 }}>检索</span>
                <span>BM25 + 向量 + 关系扩展</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted" style={{ width: 44 }}>排序</span>
                <span>融合分数 + 状态权重</span>
              </div>
            </div>

            {lastScope?.retrieval_details && (
              <div
                style={{
                  marginTop: 14,
                  paddingTop: 14,
                  borderTop: "1px solid var(--line-light)",
                }}
              >
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: "var(--text)",
                    marginBottom: 10,
                  }}
                >
                  {lastScope.retrieval_details.retrieval_skipped ? "本轮处理" : "检索阶段"}
                </div>
                {lastScope.retrieval_details.retrieval_skipped ? (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 9,
                      padding: "8px 10px",
                      borderRadius: 8,
                      background: "var(--blue-soft)",
                      border: "1px solid #d9e5ff",
                    }}
                  >
                    <span style={{ fontSize: 13, width: 16, textAlign: "center" }}>💬</span>
                    <span style={{ flex: 1, fontSize: 12, color: "var(--text)", fontWeight: 600 }}>
                      意图识别
                      {lastScope.retrieval_details.intent &&
                        ` · ${INTENT_LABEL[lastScope.retrieval_details.intent] ?? lastScope.retrieval_details.intent}`}
                    </span>
                    <span
                      className="tag blue"
                      style={{ fontSize: 10.5, padding: "1px 7px", flexShrink: 0 }}
                    >
                      无需检索
                    </span>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                    {lastScope.retrieval_details.search_query &&
                      lastScope.retrieval_details.search_query !== lastScope.question && (
                        <div
                          title={`原始问题：${lastScope.question}`}
                          style={{
                            display: "flex",
                            alignItems: "flex-start",
                            gap: 8,
                            padding: "7px 10px",
                            borderRadius: 8,
                            background: "var(--blue-soft)",
                            border: "1px solid #d9e5ff",
                            fontSize: 12,
                            color: "var(--text)",
                          }}
                        >
                          <span style={{ width: 16, textAlign: "center" }}>🔍</span>
                          <span style={{ flex: 1 }}>
                            <span className="text-muted">检索查询（指代已消解）：</span>
                            <b>{lastScope.retrieval_details.search_query}</b>
                          </span>
                        </div>
                      )}
                    <RetrievalStageRow
                      icon={STAGE_ICONS[0]}
                      label="权限过滤"
                      value={lastScope.retrieval_details.permission_filtered_experiments}
                      hint="可见实验"
                    />
                    <RetrievalStageRow
                      icon={STAGE_ICONS[1]}
                      label="状态过滤"
                      value={lastScope.retrieval_details.status_filtered_chunks}
                      hint="候选切片"
                    />
                    <RetrievalStageRow
                      icon={STAGE_ICONS[2]}
                      label="BM25 召回"
                      value={lastScope.retrieval_details.bm25_hits}
                      hint="关键词命中"
                    />
                    <RetrievalStageRow
                      icon={STAGE_ICONS[3]}
                      label="向量召回"
                      value={lastScope.retrieval_details.vector_hits}
                      hint="语义相似"
                    />
                    <RetrievalStageRow
                      icon={STAGE_ICONS[4]}
                      label="关系扩展"
                      value={lastScope.retrieval_details.after_relation_expansion}
                      hint="含关联结果/证据"
                    />
                    <RetrievalStageRow
                      icon={STAGE_ICONS[5]}
                      label="重排 Top-K"
                      value={lastScope.retrieval_details.after_rerank}
                      hint={
                        lastScope.retrieval_details.top_score != null
                          ? `top_score=${lastScope.retrieval_details.top_score.toFixed(3)}`
                          : undefined
                      }
                      highlight
                    />
                  </div>
                )}
                {lastScope.retrieval_details.elapsed_sec != null && (
                  <div
                    style={{
                      marginTop: 10,
                      paddingTop: 10,
                      borderTop: "1px solid var(--line-light)",
                      fontSize: 11,
                      color: "var(--muted)",
                      display: "flex",
                      justifyContent: "space-between",
                    }}
                  >
                    <span>检索耗时</span>
                    <span style={{ fontFamily: "JetBrains Mono, monospace" }}>
                      {lastScope.retrieval_details.elapsed_sec}s
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 降级提示（仅降级模式显示） */}
          {isDegraded && (
            <div
              className="card"
              style={{
                background: "var(--amber-soft)",
                borderColor: "#f5d99a",
                padding: 16,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  marginBottom: 8,
                }}
              >
                <span style={{ fontSize: 16 }}>⚠️</span>
                <b style={{ color: "#8a5e00", fontSize: 14 }}>降级模式</b>
              </div>
              <p
                style={{
                  fontSize: 12,
                  color: "#8a5e00",
                  lineHeight: 1.65,
                  margin: 0,
                }}
              >
                {lastScope?.model_info?.embedding_mode === "hash-fallback" && (
                  <>
                    未配置 <code style={{ background: "#ffefc4", padding: "1px 5px", borderRadius: 4, fontSize: 11 }}>QWEN_API_KEY</code>
                    ，使用 hash 伪向量（语义检索降级）。
                    <br />
                  </>
                )}
                {lastScope?.model_info?.chat_mode === "template-fallback" && (
                  <>
                    未配置 <code style={{ background: "#ffefc4", padding: "1px 5px", borderRadius: 4, fontSize: 11 }}>DEEPSEEK_API_KEY</code>
                    ，使用模板式回答（无 LLM 归纳）。
                  </>
                )}
                <span style={{ display: "block", marginTop: 6, opacity: 0.85 }}>
                  配置 API key 后重启服务可恢复完整 RAG 能力。
                </span>
              </p>
            </div>
          )}

          {/* 建议问题 */}
          <div className="card" style={{ padding: 16 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                marginBottom: 10,
              }}
            >
              <span style={{ fontSize: 16 }}>💡</span>
              <b style={{ fontSize: 14 }}>建议问题</b>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  onClick={() => ask(s.q)}
                  disabled={loading}
                  style={{
                    textAlign: "left",
                    padding: "8px 12px",
                    borderRadius: 9,
                    border: "1px solid var(--line-light)",
                    background: "#fafcff",
                    color: "var(--text)",
                    fontSize: 12.5,
                    cursor: loading ? "not-allowed" : "pointer",
                    opacity: loading ? 0.6 : 1,
                    transition: "all 0.15s ease",
                  }}
                  onMouseEnter={(e) => {
                    if (!loading) {
                      e.currentTarget.style.borderColor = "var(--blue)";
                      e.currentTarget.style.background = "var(--blue-soft)";
                      e.currentTarget.style.color = "var(--blue)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--line-light)";
                    e.currentTarget.style.background = "#fafcff";
                    e.currentTarget.style.color = "var(--text)";
                  }}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        .ai-avatar {
          width: 36px;
          height: 36px;
          border-radius: 11px;
          background: linear-gradient(135deg, #3370ff 0%, #22b8cf 100%);
          color: #fff;
          display: grid;
          place-items: center;
          flex-shrink: 0;
          box-shadow: 0 2px 8px rgba(34, 184, 207, 0.28);
        }
        .user-avatar {
          width: 36px;
          height: 36px;
          border-radius: 11px;
          background: linear-gradient(135deg, #6f7e99 0%, #4b5a74 100%);
          color: #fff;
          display: grid;
          place-items: center;
          flex-shrink: 0;
          box-shadow: 0 2px 8px rgba(75, 90, 116, 0.22);
        }
        .send-btn {
          width: 42px;
          height: 42px;
          border-radius: 11px;
          border: none;
          background: linear-gradient(135deg, #3370ff 0%, #22b8cf 100%);
          color: #fff;
          cursor: pointer;
          display: grid;
          place-items: center;
          transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1),
                      box-shadow 0.18s ease,
                      background 0.18s ease;
          box-shadow: 0 3px 10px rgba(51, 112, 255, 0.3);
          flex-shrink: 0;
          padding: 0;
        }
        .send-btn:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 6px 16px rgba(51, 112, 255, 0.42);
        }
        .send-btn:active:not(:disabled) {
          transform: translateY(0) scale(0.95);
        }
        .send-btn:disabled {
          background: linear-gradient(135deg, #c4cedd 0%, #a8b4c9 100%);
          cursor: not-allowed;
          box-shadow: none;
        }
        .send-btn svg {
          transform: translateX(1px);
        }
        .typing-dot {
          display: inline-block;
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--blue);
          animation: typingPulse 1.2s infinite ease-in-out;
        }
        @keyframes typingPulse {
          0%, 60%, 100% { opacity: 0.3; transform: scale(0.85); }
          30% { opacity: 1; transform: scale(1); }
        }
        .qa-cursor {
          display: inline-block;
          width: 7px;
          height: 14px;
          background: var(--blue);
          margin-left: 2px;
          vertical-align: text-bottom;
          animation: cursorBlink 0.9s infinite;
          border-radius: 1px;
        }
        @keyframes cursorBlink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
        .citation-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 7px 10px;
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.85);
          border: 1px solid var(--line-light);
          font-size: 12px;
          transition: all 0.15s ease;
        }
        .citation-row:hover {
          border-color: var(--blue);
          background: var(--blue-soft);
          transform: translateX(2px);
        }
        .citation-toggle {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 5px 10px 5px 8px;
          border-radius: 8px;
          border: 1px solid var(--line-light);
          background: #fafcff;
          color: var(--muted);
          font-size: 11.5px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
          font-family: inherit;
        }
        .citation-toggle:hover {
          border-color: var(--blue);
          background: var(--blue-soft);
          color: var(--blue);
        }
        .citation-toggle svg {
          transition: transform 0.18s ease;
        }
      `}</style>
    </div>
  );
}

function MessageBubble({
  m,
  navigate,
}: {
  m: Msg;
  navigate: (path: string) => void;
}) {
  const isUser = m.role === "user";
  const [citationsExpanded, setCitationsExpanded] = useState(false);
  const time = new Date(m.ts).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });

  if (isUser) {
    return (
      <div
        className="flex items-end gap-2.5"
        style={{ margin: "14px 0", justifyContent: "flex-end" }}
      >
        <div style={{ textAlign: "right" }}>
          <div
            style={{
              display: "inline-block",
              background: "linear-gradient(135deg, #3370ff 0%, #22b8cf 100%)",
              color: "#fff",
              padding: "10px 14px",
              borderRadius: 14,
              borderBottomRightRadius: 4,
              fontSize: 14,
              lineHeight: 1.6,
              maxWidth: 460,
              wordBreak: "break-word",
              whiteSpace: "pre-wrap",
              boxShadow: "0 2px 8px rgba(51, 112, 255, 0.18)",
            }}
          >
            {m.text}
          </div>
          <div
            style={{
              fontSize: 10.5,
              color: "var(--muted)",
              marginTop: 4,
              marginRight: 4,
              textAlign: "right",
            }}
          >
            {time}
          </div>
        </div>
        <div className="user-avatar">
          <UserIcon size={18} />
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex items-start gap-2.5"
      style={{ margin: "14px 0" }}
    >
      <div className="ai-avatar">
        <SparkleIcon size={18} />
      </div>
      <div style={{ flex: 1, minWidth: 0, maxWidth: 560 }}>
        <div
          style={{
            display: "inline-block",
            background: m.refused ? "var(--amber-soft)" : "var(--bg)",
            border: m.refused
              ? "1px solid #f5d99a"
              : "1px solid var(--line-light)",
            color: "var(--text)",
            padding: "10px 14px",
            borderRadius: 14,
            borderBottomLeftRadius: 4,
            fontSize: 14,
            lineHeight: 1.65,
            wordBreak: "break-word",
            whiteSpace: "pre-wrap",
            maxWidth: "100%",
          }}
        >
          {m.refused && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                marginBottom: 6,
                color: "#8a5e00",
                fontWeight: 700,
                fontSize: 13,
              }}
            >
              <span>⚠</span> 系统拒答
            </div>
          )}
          {m.warning && (
            <div
              style={{
                background: "#fff3d6",
                color: "#8a5e00",
                fontSize: 12,
                padding: "6px 10px",
                borderRadius: 7,
                marginBottom: 8,
                border: "1px solid #f5d99a",
              }}
            >
              ⚠ 该结论尚未经实验结果验证，仅作参考
            </div>
          )}
          <div>
            {m.text}
            {m.streamed && <span className="qa-cursor" />}
          </div>
        </div>

        {/* 引用卡片（可折叠） */}
        {m.citations && m.citations.length > 0 && !m.streamed && (
          <div style={{ marginTop: 8 }}>
            <button
              className="citation-toggle"
              onClick={() => setCitationsExpanded((v) => !v)}
              aria-expanded={citationsExpanded}
            >
              <ChevronIcon expanded={citationsExpanded} />
              <span>证据来源 · {m.citations.length} 条</span>
            </button>
            {citationsExpanded && (
              <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 6 }}>
              {m.citations.map((c, j) => {
                const tag = c.knowledge_status
                  ? KNOWLEDGE_TAG[c.knowledge_status]
                  : null;
                const color = CITATION_COLOR[c.type];
                return (
                  <div
                    key={j}
                    className="citation-row"
                    style={{ borderLeft: `3px solid ${color}` }}
                  >
                    <span style={{ fontSize: 15, flexShrink: 0 }}>
                      {CITATION_ICON[c.type]}
                    </span>
                    <span
                      style={{
                        fontFamily: "JetBrains Mono, monospace",
                        fontSize: 11,
                        color: "var(--muted)",
                        flexShrink: 0,
                      }}
                    >
                      [{c.ref}]
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color,
                        flexShrink: 0,
                        fontWeight: 600,
                      }}
                    >
                      {CITATION_LABEL[c.type]}
                    </span>
                    <span
                      style={{
                        flex: 1,
                        minWidth: 0,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        color: "var(--text)",
                      }}
                      title={c.title}
                    >
                      {c.title}
                    </span>
                    {tag && (
                      <span
                        className={`tag ${tag.cls}`}
                        style={{ padding: "1px 7px", fontSize: 10, flexShrink: 0 }}
                      >
                        {tag.label}
                      </span>
                    )}
                    {c.url && (
                      <button
                        onClick={() => navigate(c.url!)}
                        style={{
                          color: "var(--blue)",
                          fontSize: 11.5,
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          padding: 0,
                          flexShrink: 0,
                          fontWeight: 500,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.textDecoration = "underline";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.textDecoration = "none";
                        }}
                      >
                        查看 →
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
            )}
          </div>
        )}

        {/* 拒答原因 */}
        {m.refused && m.missingConditions && m.missingConditions.length > 0 && (
          <div
            style={{
              marginTop: 8,
              padding: "10px 12px",
              borderRadius: 9,
              background: "#fff6df",
              border: "1px solid #f5d99a",
              fontSize: 12,
              color: "#8a5e00",
            }}
          >
            <div style={{ fontWeight: 700, marginBottom: 5 }}>需补充条件：</div>
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
              {m.missingConditions.map((mc, j) => (
                <li key={j}>{mc}</li>
              ))}
            </ul>
          </div>
        )}

        {/* 时间戳 */}
        {!m.streamed && (
          <div
            style={{
              fontSize: 10.5,
              color: "var(--muted)",
              marginTop: 4,
              marginLeft: 4,
            }}
          >
            {time}
          </div>
        )}
      </div>
    </div>
  );
}

function RetrievalStageRow({
  icon,
  label,
  value,
  hint,
  highlight,
}: {
  icon: string;
  label: string;
  value?: number;
  hint?: string;
  highlight?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9,
        padding: highlight ? "7px 10px" : "5px 10px",
        borderRadius: 8,
        background: highlight ? "var(--blue-soft)" : "transparent",
        border: highlight ? "1px solid #d9e5ff" : "1px solid transparent",
      }}
    >
      <span style={{ fontSize: 13, width: 16, textAlign: "center" }}>{icon}</span>
      <span
        style={{
          flex: 1,
          fontSize: 12,
          color: "var(--text)",
          fontWeight: highlight ? 600 : 500,
        }}
      >
        {label}
      </span>
      <span style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
        <b
          style={{
            fontSize: 13.5,
            color: highlight ? "var(--blue)" : "var(--text)",
            fontFamily: "JetBrains Mono, monospace",
          }}
        >
          {value ?? "-"}
        </b>
        {hint && (
          <span style={{ fontSize: 10.5, color: "var(--muted)" }}>{hint}</span>
        )}
      </span>
    </div>
  );
}

function SparkleIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 1.5l2.7 7.8 7.8 2.7-7.8 2.7L12 22.5l-2.7-7.8L1.5 12l7.8-2.7L12 1.5z" />
    </svg>
  );
}

function UserIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M5 21v-1a7 7 0 0114 0v1" />
    </svg>
  );
}

function SendIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M22 2L11 13" />
      <path d="M22 2l-7 20-4-9-9-4 20-7z" />
    </svg>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      width={12}
      height={12}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}
      aria-hidden="true"
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}
