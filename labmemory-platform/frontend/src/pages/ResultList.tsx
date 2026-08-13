import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiListMeetings } from "../api";
import type { MeetingChainItem } from "../types";

type Tab = "pending" | "published" | "submitted" | "all";

export default function ResultList() {
  const [tab, setTab] = useState<Tab>("pending");
  const [data, setData] = useState<MeetingChainItem[]>([]);
  const [err, setErr] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    apiListMeetings()
      .then((d) => setData(d as unknown as MeetingChainItem[]))
      .catch((e) => setErr(e.message));
  }, []);

  // 已启动任务的会议（running/completed；audited/blocked/needs_confirmation 未进入执行链路不展示）
  const withTask = useMemo(
    () =>
      data.filter((m) => {
        const s = m.task?.status;
        return s === "running" || s === "completed";
      }),
    [data]
  );

  // 待提交：任务在运行中 或 已完成但还没有任何结果
  const toSubmit = useMemo(
    () =>
      withTask.filter((m) => {
        const status = m.task?.status;
        if (status === "running") return true;
        if (status === "completed") return !m.results?.length;
        return false;
      }),
    [withTask]
  );

  // 待发布：有 submitted 状态结果但还没 published
  const submitted = useMemo(
    () =>
      withTask.filter((m) =>
        m.results?.some((r) => r.status === "submitted")
      ),
    [withTask]
  );

  // 已发布：至少有一个 published 结果
  const published = useMemo(
    () =>
      withTask.filter((m) =>
        m.results?.some((r) => r.status === "published")
      ),
    [withTask]
  );

  const stats = useMemo(
    () => ({
      pending: toSubmit.length,
      submitted: submitted.length,
      published: published.length,
      all: withTask.length,
    }),
    [toSubmit, submitted, published, withTask]
  );

  const filtered =
    tab === "pending"
      ? toSubmit
      : tab === "submitted"
      ? submitted
      : tab === "published"
      ? published
      : withTask;

  const TAB_LABEL: Record<Tab, string> = {
    pending: "待提交",
    submitted: "待发布",
    published: "已发布",
    all: "全部",
  };

  const EMPTY_TEXT: Record<Tab, { title: string; desc: string }> = {
    pending: {
      title: "暂无待提交结果",
      desc: "任务运行完成后可在此处提交实际参数与指标。",
    },
    submitted: {
      title: "暂无待发布结果",
      desc: "执行人提交的结果会出现在这里，等待 PI/Lead 发布为知识。",
    },
    published: {
      title: "暂无已发布结果",
      desc: "经 PI/Lead 确认发布的结果会沉淀为知识，出现在实验护照中。",
    },
    all: {
      title: "暂无任务",
      desc: "会议复核通过并生成任务后，会出现在这里。",
    },
  };

  return (
    <div className="fade-in">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="tabs">
          {(["pending", "submitted", "published", "all"] as Tab[]).map((t) => (
            <button
              key={t}
              className={`tab ${tab === t ? "active" : ""}`}
              onClick={() => setTab(t)}
            >
              {TAB_LABEL[t]}
              <span className="count">{stats[t]}</span>
            </button>
          ))}
        </div>
        <span className="text-xs muted">当前显示 {filtered.length} / 共 {withTask.length} 个任务</span>
      </div>

      {err && <div className="alert-inline error"><span className="ai-icon">⚠</span><span>{err}</span></div>}

      <div className="space-y-3">
        {filtered.length === 0 && (
          <div className="card">
            <div className="empty-state">
              <div className="empty-icon">📊</div>
              <div className="empty-title">{EMPTY_TEXT[tab].title}</div>
              <div className="empty-desc">{EMPTY_TEXT[tab].desc}</div>
            </div>
          </div>
        )}
        {filtered.map((m) => {
          const t = m.task!;
          const results = m.results || [];
          const hasPublished = results.some((r) => r.status === "published");
          const hasSubmitted = results.some((r) => r.status === "submitted");
          const hasNoResults = results.length === 0;
          return (
            <div
              key={m.meeting_id}
              className="card p-4 cursor-pointer transition-all group hover:shadow-md"
              onClick={() => navigate(`/result/${t.task_id}`)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <h3 className="font-semibold text-base group-hover:text-blue-600 transition">
                      {m.title}
                    </h3>
                    <span className={`tag ${hasPublished ? "green" : hasSubmitted ? "amber" : "blue"}`}>
                      {hasPublished ? "已发布" : hasSubmitted ? "待发布" : hasNoResults ? "待提交" : t.status}
                    </span>
                  </div>
                  <div className="meta-row mb-2">
                    <span className="mono">{t.task_id}</span>
                    <span className="sep" />
                    <span>任务状态：{t.status}</span>
                    <span className="sep" />
                    <span>{results.length} 条结果</span>
                  </div>
                  {results.length > 0 && (
                    <div className="flex gap-2 mt-2 text-xs flex-wrap">
                      {results.slice(0, 3).map((r) => (
                        <div
                          key={r.result_id}
                          className="px-2.5 py-1 rounded-lg"
                          style={{ background: "var(--bg)", border: "1px solid var(--line-light)" }}
                        >
                          <span className="text-slate-500 mr-1.5 mono">{r.result_id.slice(0, 10)}</span>
                          <span className="font-mono font-medium">
                            {r.knowledge_status || r.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <button className="btn sm ghost opacity-0 group-hover:opacity-100 transition">
                  查看 →
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
