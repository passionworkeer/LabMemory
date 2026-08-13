import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiGetPassport } from "../api";
import { Loading } from "../components/State";
import type { ExperimentPassport } from "../types";

export default function ExperimentPassport() {
  const { experimentId } = useParams<{ experimentId: string }>();
  const [data, setData] = useState<ExperimentPassport | null>(null);
  const [err, setErr] = useState("");

  const load = (id: string) => {
    if (!id) return;
    apiGetPassport(id).then(setData).catch((e) => setErr(e.message));
  };
  useEffect(() => {
    if (experimentId) load(experimentId);
  }, [experimentId]);

  return (
    <div className="fade-in">
      {err && <div className="alert-inline error"><span className="ai-icon">⚠</span><span>{err}</span></div>}

      {!data && !err && <Loading />}

      {data && (
        <>
          <div className="card mb-5">
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div className="min-w-0">
                <h2 className="text-lg font-bold">{data.name}</h2>
                <div className="meta-row mt-1.5">
                  <span className="mono">{data.experiment_id}</span>
                  <span className="sep" />
                  <span>项目 {data.project_id}</span>
                  <span className="sep" />
                  <span>状态 {data.status}</span>
                </div>
              </div>
            </div>
            {data.current_claim ? (
              <div
                className="rounded-xl p-3.5 text-sm mt-4"
                style={{
                  background: "var(--blue-soft)",
                  border: "1px solid #c5d9ff",
                }}
              >
                <div className="font-semibold flex items-center gap-2 flex-wrap">
                  当前主张 <span className="font-mono text-xs">{data.current_claim.claim_id}</span>
                  <span className="tag blue">{data.current_claim.status}</span>
                  {data.current_claim.knowledge_status && (
                    <span className={`tag ${data.current_claim.knowledge_status === "supported" ? "green" : "amber"}`}>
                      {data.current_claim.knowledge_status}
                    </span>
                  )}
                </div>
                {data.current_claim.parameter_version && (
                  <details className="mt-2 text-xs">
                    <summary className="cursor-pointer text-muted hover:text-slate-700">
                      参数版本 {data.current_claim.parameter_version.version}
                    </summary>
                    <ParameterVersionView pv={data.current_claim.parameter_version} />
                  </details>
                )}
              </div>
            ) : (
              <p className="text-muted text-sm mt-3">暂无当前主张</p>
            )}
          </div>

          <div className="section-title">
            <b>数据关系链</b>
            <span className="section-meta">{data.meetings.length} 个会议</span>
          </div>
          {data.meetings.length === 0 ? (
            <div className="card">
              <div className="empty-state">
                <div className="empty-icon">🔗</div>
                <div className="empty-title">暂无会议</div>
              </div>
            </div>
          ) : (
            data.meetings.map((m) => {
              const r = m.review;
              const claim = m.claim;
              const task = m.task;
              const audit = m.audit;
              const results = m.results;
              const pv = claim?.parameter_version;
              return (
                <div className="card mb-3" key={m.meeting_id}>
                  <div className="flex justify-between items-start mb-2.5 flex-wrap gap-2">
                    <div className="min-w-0">
                      <h3 className="font-semibold text-sm">{m.title}</h3>
                      <p className="text-xs text-muted font-mono mt-0.5">{m.meeting_id}</p>
                    </div>
                    <span
                      className={`tag ${
                        r?.decision === "confirmed" ? "green" : r?.decision === "ended" ? "red" : "blue"
                      }`}
                    >
                      {r?.decision || r?.status || "pending"}
                    </span>
                  </div>
                  <div className="grid grid-cols-5 gap-2 text-xs">
                    <PassportNode label="复核" value={r?.status || "-"} sub={r?.modifications ? "已修改" : "原样"} />
                    <PassportNode label="主张" value={claim ? claim.claim_id : "-"} sub={claim ? claim.status : "-"} />
                    <PassportNode
                      label="任务"
                      value={task ? task.status : "-"}
                      sub={task ? task.task_id.slice(0, 12) : "-"}
                      mono
                    />
                    <PassportNode
                      label="审计"
                      value={audit ? audit.status : "-"}
                      sub={audit?.result?.overall || ""}
                    />
                    <PassportNode
                      label="结果"
                      value={`${results.length} 条`}
                      sub={results.map((r) => r.status).join(",") || "-"}
                    />
                  </div>
                  {pv && (
                    <details className="mt-3 text-xs">
                      <summary className="cursor-pointer text-muted hover:text-slate-700">
                        参数版本 {pv.version}
                      </summary>
                      <ParameterVersionView pv={pv} />
                    </details>
                  )}
                </div>
              );
            })
          )}

          <div className="section-title" style={{ marginTop: 24 }}>
            <b>统一时间线</b>
            <span className="section-meta">{data.timeline.length} 个事件</span>
          </div>
          <div className="card">
            {data.timeline.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📅</div>
                <div className="empty-title">暂无事件</div>
              </div>
            ) : (
              <div className="timeline">
                {data.timeline
                  .slice()
                  .reverse()
                  .map((e, i) => (
                    <div className="event" key={i}>
                      <small className="text-muted">{new Date(e.timestamp).toLocaleString()}</small>
                      <b className="block mt-1 text-sm">
                        <span className="text-blue-600 font-mono">{e.event_type}</span>
                        <span className="text-muted ml-2 font-normal">
                          {e.target_type}:{e.target_id}
                        </span>
                      </b>
                      <p className="text-sm text-slate-600 mt-0.5">{e.summary}</p>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

interface ParameterVersionShape {
  version?: string;
  effective_at?: string;
  parameters?: { name: string; value: string; unit?: string }[];
  scope?: Record<string, unknown>;
}

function ParameterVersionView({ pv }: { pv: ParameterVersionShape }) {
  const params = pv.parameters || [];
  const scopeEntries = Object.entries(pv.scope || {});
  const showExtra = scopeEntries.length > 0 || !!pv.effective_at;
  if (params.length === 0 && !showExtra) {
    return <div className="mt-2 text-xs text-muted">暂无参数</div>;
  }
  return (
    <div className="mt-2 rounded-lg p-3 text-xs space-y-2" style={{ background: "var(--line-light)" }}>
      {params.length > 0 && (
        <div className="space-y-1.5">
          {params.map((p, i) => (
            <div key={i} className="flex items-baseline gap-2">
              <span className="text-slate-500 w-20 shrink-0 truncate">{p.name}</span>
              <span className="font-bold text-slate-800">{p.value}</span>
              {p.unit && <span className="text-muted">{p.unit}</span>}
            </div>
          ))}
        </div>
      )}
      {showExtra && (
        <div className="pt-2 border-t border-slate-200/70 space-y-1.5">
          {scopeEntries.length > 0 && (
            <div>
              <span className="text-slate-500 mr-1">适用范围：</span>
              <span className="text-slate-700">
                {scopeEntries.map(([k, v]) => `${k}=${String(v)}`).join(" / ")}
              </span>
            </div>
          )}
          {pv.effective_at && (
            <div>
              <span className="text-slate-500 mr-1">生效时间：</span>
              <span className="text-slate-700">{new Date(pv.effective_at).toLocaleString()}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PassportNode({
  label,
  value,
  sub,
  mono,
}: {
  label: string;
  value: string;
  sub: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-lg p-2.5" style={{ background: "var(--bg)", border: "1px solid var(--line-light)" }}>
      <div className="text-muted text-xs mb-0.5">{label}</div>
      <div className={`font-semibold text-sm ${mono ? "font-mono" : ""}`}>{value}</div>
      <div className="text-slate-400 text-xs mt-0.5">{sub}</div>
    </div>
  );
}
