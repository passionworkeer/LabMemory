import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiListPassports } from "../api";
import type { PassportSummaryOut } from "../types";

const ROLE_LABEL: Record<string, string> = { pi: "PI", lead: "Lead", executor: "Exec" };

function fmtActivity(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? `今天 ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
    : d.toLocaleDateString([], { month: "2-digit", day: "2-digit" });
}

function knowledgeTag(k: string | null | undefined) {
  if (k === "supported") return <span className="tag green">支持</span>;
  if (k === "partially_supported") return <span className="tag amber">部分支持</span>;
  if (k === "refuted") return <span className="tag red">推翻</span>;
  return <span className="tag gray">未验证</span>;
}

export default function PassportList() {
  const [items, setItems] = useState<PassportSummaryOut[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const load = () => {
    setBusy(true);
    apiListPassports()
      .then(setItems)
      .catch((e) => setErr(e.message))
      .finally(() => setBusy(false));
  };
  useEffect(load, []);

  const stats = useMemo(
    () => ({
      total: items.length,
      active: items.filter((i) => i.status === "active").length,
      pendingReviews: items.reduce((s, i) => s + i.pending_review_count, 0),
      published: items.reduce((s, i) => s + i.published_result_count, 0),
    }),
    [items]
  );

  const summaryChips = [
    { label: "实验总数", value: stats.total, color: "var(--blue)", bg: "var(--blue-soft)" },
    { label: "进行中", value: stats.active, color: "var(--green)", bg: "var(--green-soft)" },
    { label: "待复核会议", value: stats.pendingReviews, color: "var(--amber)", bg: "var(--amber-soft)" },
    { label: "已发布知识", value: stats.published, color: "var(--purple)", bg: "var(--purple-soft)" },
  ];

  return (
    <div className="fade-in">
      {/* 汇总徽标 */}
      {items.length > 0 && (
        <div className="flex gap-2 flex-wrap mb-5">
          {summaryChips.map((c) => (
            <div
              key={c.label}
              className="px-3.5 py-2 rounded-xl flex items-center gap-2.5"
              style={{ background: c.bg }}
            >
              <strong className="text-lg leading-none" style={{ color: c.color }}>
                {c.value}
              </strong>
              <span className="text-xs text-slate-600">{c.label}</span>
            </div>
          ))}
        </div>
      )}

      {err && <div className="text-red-500 text-sm mb-3">{err}</div>}

      {busy && !items.length ? (
        <div className="text-slate-400 text-sm py-10 text-center">加载中...</div>
      ) : items.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-icon">🧪</div>
            <div className="empty-title">暂无实验</div>
            <div className="empty-desc">当前账号暂无可查看的实验护照。</div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 max-lg:grid-cols-1 gap-4">
          {items.map((e) => (
            <div
              key={e.experiment_id}
              className="card passport-card cursor-pointer"
              onClick={() => navigate(`/passport/${e.experiment_id}`)}
            >
              {/* 头部：名称 + 状态 */}
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="min-w-0">
                  <h3 className="font-semibold text-slate-800 truncate flex items-center gap-2">
                    <span className="badge-dot blue" />
                    {e.name}
                  </h3>
                  <div className="meta-row mt-1.5">
                    <span className="mono">{e.experiment_id}</span>
                    <span className="sep" />
                    <span>项目 {e.project_id}</span>
                  </div>
                </div>
                <span className={`tag ${e.status === "active" ? "green" : "gray"}`}>
                  {e.status === "active" ? "进行中" : e.status}
                </span>
              </div>

              {/* 负责人 + 成员 */}
              <div className="flex flex-wrap items-center gap-1.5 mb-4">
                <span
                  className="text-xs font-semibold px-2.5 py-1 rounded-full"
                  style={{ background: "var(--purple-soft)", color: "var(--purple)" }}
                >
                  {e.owner_display_name || "-"} 负责
                </span>
                {e.members.map((m) => (
                  <span key={m.id} className="tag blue" style={{ padding: "2px 9px", fontWeight: 500 }}>
                    {m.display_name}
                    <span className="opacity-60 ml-1">{ROLE_LABEL[m.role] || m.role}</span>
                  </span>
                ))}
              </div>

              {/* 数据链统计 */}
              <div className="grid grid-cols-4 gap-2 mb-4">
                <PassportStat value={e.meeting_count} label="会议" color="var(--blue)" />
                <PassportStat
                  value={e.pending_review_count}
                  label="待复核"
                  color={e.pending_review_count > 0 ? "var(--amber)" : "var(--muted)"}
                />
                <PassportStat
                  value={e.blocked_task_count}
                  label="阻断"
                  color={e.blocked_task_count > 0 ? "var(--red)" : "var(--muted)"}
                />
                <PassportStat value={e.published_result_count} label="已发布知识" color="var(--green)" />
              </div>

              {/* 底部：当前主张 + 最近活动 + 查看 */}
              <div
                className="flex items-center justify-between gap-2 pt-3 border-t border-line-light"
              >
                <div className="min-w-0 flex items-center gap-2 flex-wrap">
                  {e.current_claim ? (
                    <>
                      <span className="font-mono text-xs text-slate-600 truncate">
                        主张 {e.current_claim.claim_id}
                      </span>
                      {knowledgeTag(e.current_claim.knowledge_status)}
                    </>
                  ) : (
                    <span className="text-xs muted">暂无当前主张</span>
                  )}
                  <span className="text-xs text-slate-400 ml-1">最近活动 {fmtActivity(e.last_activity_at)}</span>
                </div>
                <span className="btn sm primary flex-shrink-0" style={{ padding: "5px 12px" }}>
                  查看护照 →
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PassportStat({
  value,
  label,
  color,
  sub,
}: {
  value: number;
  label: string;
  color: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg py-2 px-1 text-center" style={{ background: "var(--bg)", border: "1px solid var(--line-light)" }}>
      <div className="text-lg font-bold leading-none" style={{ color }}>
        {value}
      </div>
      <div className="text-xs text-slate-500 mt-1">{sub || label}</div>
    </div>
  );
}
