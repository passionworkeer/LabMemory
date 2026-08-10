import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiListMeetings } from "../api";
import type { MeetingChainItem } from "../types";

type Tab = "pending" | "blocked" | "passed" | "all";

export default function AuditList() {
  const [tab, setTab] = useState<Tab>("pending");
  const [data, setData] = useState<MeetingChainItem[]>([]);
  const [err, setErr] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    apiListMeetings()
      .then((d) => setData(d as unknown as MeetingChainItem[]))
      .catch((e) => setErr(e.message));
  }, []);

  // 审计列表只展示尚未完成的任务（完成后进入结果回流）
  const withTask = useMemo(
    () => data.filter((m) => m.task && m.task.status !== "completed"),
    [data]
  );

  const stats = useMemo(
    () => ({
      pending: withTask.filter(
        (m) => !m.audit || m.audit.status === "pending" || m.task?.status === "draft"
      ).length,
      blocked: withTask.filter((m) => m.task?.status === "blocked").length,
      passed: withTask.filter((m) => m.audit?.status === "passed").length,
      all: withTask.length,
    }),
    [withTask]
  );

  const filtered = useMemo(() => {
    if (tab === "all") return withTask;
    if (tab === "blocked")
      return withTask.filter((m) => m.task?.status === "blocked");
    if (tab === "passed")
      return withTask.filter((m) => m.audit?.status === "passed");
    // pending: 还没审计 或 审计中 或 任务还在 draft
    return withTask.filter(
      (m) => !m.audit || m.audit.status === "pending" || m.task?.status === "draft"
    );
  }, [withTask, tab]);

  const EMPTY_TEXT: Record<Tab, { title: string; desc: string }> = {
    pending: {
      title: "暂无待审计任务",
      desc: "任务生成后会自动出现在这里，等待行动前审计。",
    },
    blocked: {
      title: "暂无已阻断任务",
      desc: "引用过期参数版本的任务会自动阻断，可一键修正到新版本。",
    },
    passed: {
      title: "暂无已通过任务",
      desc: "通过五项审计检查的任务会出现在这里，可以启动执行。",
    },
    all: {
      title: "暂无任务",
      desc: "会议复核通过并生成任务后，会出现在这里。",
    },
  };

  const TAB_LABEL: Record<Tab, string> = {
    pending: "待审计",
    blocked: "已阻断",
    passed: "已通过",
    all: "全部任务",
  };

  return (
    <div className="fade-in">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="tabs">
          {(["pending", "blocked", "passed", "all"] as Tab[]).map((t) => (
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

      {err && <div className="text-red-500 mb-3 text-sm">{err}</div>}

      <div className="space-y-3">
        {filtered.length === 0 && (
          <div className="card">
            <div className="empty-state">
              <div className="empty-icon">🛡</div>
              <div className="empty-title">{EMPTY_TEXT[tab].title}</div>
              <div className="empty-desc">{EMPTY_TEXT[tab].desc}</div>
            </div>
          </div>
        )}
        {filtered.map((m) => {
          const t = m.task!;
          const a = m.audit;
          const isBlocked = t.status === "blocked" || a?.status === "blocked";
          const isPassed = a?.status === "passed";
          return (
            <div
              key={m.meeting_id}
              className={`card p-4 cursor-pointer transition-all group hover:shadow-md ${
                isBlocked ? "border-red-200" : isPassed ? "border-green-200" : ""
              }`}
              onClick={() => navigate(`/audit/${t.task_id}`)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <h3 className="font-semibold text-base group-hover:text-blue-600 transition">
                      {m.title}
                    </h3>
                    <span className={`tag ${isBlocked ? "red" : isPassed ? "green" : "amber"}`}>
                      {isBlocked ? "已阻断" : isPassed ? "已通过" : "待审计"}
                    </span>
                  </div>
                  <div className="meta-row mb-2">
                    <span className="mono">{t.task_id}</span>
                    <span className="sep" />
                    <span>实验：{m.claim?.experiment_id || "-"}</span>
                  </div>
                  <div className="flex gap-3 mt-2 text-xs flex-wrap">
                    {["版本单位", "证据范围", "审批", "资源", "失败边界"].map((c, i) => {
                      const checks = a?.checks as Record<string, { status: string }> | undefined;
                      const keys = ["version_unit", "evidence_scope", "approval", "resource", "failure_boundary"];
                      const status = checks?.[keys[i]]?.status;
                      return (
                        <div key={c} className="flex items-center gap-1.5">
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{
                              background:
                                status === "passed"
                                  ? "var(--green)"
                                  : status === "failed"
                                  ? "var(--red)"
                                  : "var(--amber)",
                            }}
                          />
                          <span className="text-slate-500">{c}</span>
                        </div>
                      );
                    })}
                  </div>
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
