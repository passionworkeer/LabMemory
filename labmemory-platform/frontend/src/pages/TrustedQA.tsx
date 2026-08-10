import { useState } from "react";
import { apiAskQuestion } from "../api";
import type { QAAnswerOut } from "../types";
import { useAuth } from "../store";

interface Msg {
  role: "user" | "ai";
  text: string;
  citations?: { type: string; id?: string; knowledge_status?: string; metrics?: unknown; speaker?: string; text?: string }[];
  refused?: boolean;
}

const ROLE_LABEL: Record<string, string> = {
  pi: "项目负责人",
  lead: "实验负责人",
  executor: "执行人",
  admin: "管理员",
};

export default function TrustedQA() {
  const [question, setQuestion] = useState("EXP-DEMO-001 当前推荐温度是多少？");
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: "user",
      text: "EXP-DEMO-001 当前推荐温度是多少？",
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [lastScope, setLastScope] = useState<Record<string, unknown> | null>(null);
  const { user } = useAuth();

  const ask = async (q?: string) => {
    const text = (q ?? question).trim();
    if (!text || loading) return;
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);
    try {
      const r: QAAnswerOut = await apiAskQuestion(text);
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          text: r.answer,
          citations: r.citations,
          refused: r.refused,
        },
      ]);
      setLastScope(r.retrieval_scope);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "ai", text: `查询失败：${(e as Error).message}`, refused: true },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fade-in">
      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 340px" }}>
        <div className="card flex flex-col" style={{ height: 580 }}>
          <div className="flex-1 overflow-auto" style={{ maxHeight: 510 }}>
            {messages.map((m, i) => (
              <div
                key={i}
                className={`max-w-[80%] p-3 rounded-xl my-2 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "ml-auto text-white"
                    : ""
                }`}
                style={
                  m.role === "user"
                    ? { background: "var(--blue)", borderBottomRightRadius: 4 }
                    : { background: "var(--bg)", borderBottomLeftRadius: 4, border: "1px solid var(--line-light)" }
                }
              >
                {m.role === "ai" && m.refused && (
                  <b className="text-amber-700 block mb-1.5 flex items-center gap-1.5">
                    <span>⚠</span> 系统拒答
                  </b>
                )}
                <div>{m.text}</div>
                {m.citations && m.citations.length > 0 && (
                  <div className="border-t border-slate-300/40 mt-2 pt-2 text-xs text-blue-600 flex flex-wrap gap-2">
                    <span className="text-muted">证据来源：</span>
                    {m.citations.map((c, j) => (
                      <span key={j} className="font-mono">
                        [{c.type}
                        {c.id ? `:${c.id}` : ""}
                        {c.knowledge_status ? `(${c.knowledge_status})` : ""}]
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="text-muted text-sm text-center py-3 flex items-center justify-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" style={{ animationDelay: "0.2s" }} />
                <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" style={{ animationDelay: "0.4s" }} />
                <span className="ml-1">检索中...</span>
              </div>
            )}
          </div>
          <div className="flex gap-2 border-t border-line pt-3">
            <input
              className="input"
              placeholder="输入问题，例如：EXP-DEMO-001 当前参数版本？"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
            />
            <button className="btn primary" onClick={() => ask()} disabled={loading || !question.trim()}>
              提问
            </button>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="card">
            <div className="section-title">
              <b>本次检索范围</b>
            </div>
            <div className="text-xs space-y-1.5 leading-relaxed">
              <div className="flex items-center gap-2">
                <span className="text-muted">身份：</span>
                <span>{user?.display_name}</span>
                {user && <span className="text-muted">（{ROLE_LABEL[user.global_role] || user.global_role}）</span>}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted">状态：</span>
                <span>当前有效、部分支持、待验证</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted">召回：</span>
                <span>Claim + Result 关键词检索</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted">排序：</span>
                <span>关键词匹配数 + 时间新鲜度</span>
              </div>
              {lastScope && (
                <div className="mt-2 pt-2 border-t border-line-light">
                  <div>匹配主张数：<b>{String(lastScope.matched_claims ?? "-")}</b></div>
                  <div>检索实验数：<b>{String(lastScope.searched_experiments ?? "-")}</b></div>
                </div>
              )}
            </div>
          </div>
          <div className="card">
            <div className="section-title">
              <b>系统可明确拒答</b>
            </div>
            <p className="text-muted text-sm leading-relaxed">
              若没有满足证据和权限要求的结论，系统会说明"暂无可靠结论"，并列出需要补充的条件，
              而不是编造答案。
            </p>
          </div>
          <div className="card">
            <div className="section-title">
              <b>建议问题</b>
            </div>
            <ul className="space-y-1.5 text-sm">
              <li>
                <button className="text-blue-600 hover:underline text-left" onClick={() => ask("EXP-DEMO-001 当前参数版本？")}>
                  → EXP-DEMO-001 当前参数版本？
                </button>
              </li>
              <li>
                <button className="text-blue-600 hover:underline text-left" onClick={() => ask("温度推荐值是多少？")}>
                  → 温度推荐值是多少？
                </button>
              </li>
              <li>
                <button className="text-blue-600 hover:underline text-left" onClick={() => ask("催化剂 0.8 eq 是否验证？")}>
                  → 催化剂 0.8 eq 是否验证？
                </button>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
