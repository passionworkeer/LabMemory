import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiListMeetings } from "../api";
import type { MeetingChainItem } from "../types";

type Tab = "pending" | "processed" | "all";

export default function ReviewsList() {
  const [tab, setTab] = useState<Tab>("pending");
  const [data, setData] = useState<MeetingChainItem[]>([]);
  const [err, setErr] = useState("");
  const navigate = useNavigate();

  // 一次性加载全部会议，前端按 tab 过滤
  // 这样 stats 始终反映真实总数，不会因切换 tab 而失真
  useEffect(() => {
    apiListMeetings()
      .then((d) => setData(d as unknown as MeetingChainItem[]))
      .catch((e) => setErr(e.message));
  }, []);

  const stats = useMemo(
    () => ({
      pending: data.filter((m) => m.review?.status === "pending").length,
      processed: data.filter((m) => m.review?.status === "processed").length,
      all: data.length,
    }),
    [data]
  );

  const filtered = useMemo(() => {
    if (tab === "all") return data;
    return data.filter((m) => m.review?.status === tab);
  }, [data, tab]);

  return (
    <div className="fade-in">
      {/* Tabs + Stats */}
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="tabs">
          {(["pending", "processed", "all"] as Tab[]).map((t) => (
            <button
              key={t}
              className={`tab ${tab === t ? "active" : ""}`}
              onClick={() => setTab(t)}
            >
              {t === "pending" ? "待处理" : t === "processed" ? "已处理" : "全部"}
              <span className="count">{stats[t]}</span>
            </button>
          ))}
        </div>
        <span className="text-xs muted">当前显示 {filtered.length} / 共 {data.length} 条会议记录</span>
      </div>

      {err && <div className="alert-inline error"><span className="ai-icon">⚠</span><span>{err}</span></div>}

      {/* List */}
      <div className="space-y-3">
        {filtered.length === 0 && (
          <div className="card">
            <div className="empty-state">
              <div className="empty-icon">📋</div>
              <div className="empty-title">
                {tab === "pending" ? "暂无待复核会议" : tab === "processed" ? "暂无已处理会议" : "暂无会议记录"}
              </div>
              <div className="empty-desc">
                {tab === "pending"
                  ? "新会议接入后会出现在这里，可确认决策或直接结束。"
                  : "切换其他标签查看更多会议。"}
              </div>
            </div>
          </div>
        )}
        {filtered.map((m) => (
          <div
            key={m.meeting_id}
            className="card p-4 cursor-pointer hover:shadow-md transition-all group"
            onClick={() => navigate(`/review/${m.meeting_id}`)}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                  <h3 className="font-semibold text-base group-hover:text-blue-600 transition">
                    {m.title}
                  </h3>
                  <span className={`tag ${m.review?.status === "pending" ? "amber" : m.review?.decision === "ended" ? "red" : "green"}`}>
                    {m.review?.status === "pending" ? "待复核" : m.review?.decision}
                  </span>
                </div>
                <div className="meta-row mb-2">
                  <span className="mono">{m.meeting_id}</span>
                  <span className="sep" />
                  <span>{m.captured_at ? new Date(m.captured_at).toLocaleString() : "时间未记录"}</span>
                </div>

                {/* 进度条 */}
                <div className="flex items-center gap-2 mt-3 text-xs flex-wrap">
                  {[
                    { label: "复核", done: m.review?.status === "processed" },
                    { label: "主张", done: !!m.claim },
                    { label: "任务", done: !!m.task, status: m.task?.status },
                    { label: "审计", done: !!m.audit, status: m.audit?.status },
                    { label: "结果", done: (m.results?.length || 0) > 0 },
                  ].map((step, i) => (
                    <div key={i} className="flex items-center gap-1.5">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{
                          background: step.done
                            ? step.status === "blocked"
                              ? "var(--red)"
                              : "var(--green)"
                            : "var(--line)",
                        }}
                      />
                      <span className={step.done ? "text-slate-600 font-medium" : "text-slate-400"}>
                        {step.label}
                        {step.status && (
                          <span className="text-slate-400 ml-0.5">({step.status})</span>
                        )}
                      </span>
                      {i < 4 && <span className="text-slate-300 mx-0.5">·</span>}
                    </div>
                  ))}
                </div>
              </div>
              <button
                className="btn sm ghost opacity-0 group-hover:opacity-100 transition"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/review/${m.meeting_id}`);
                }}
              >
                查看 →
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
