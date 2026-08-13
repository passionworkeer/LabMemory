import { useEffect, useState } from "react";
import { Loading, ErrorState } from "../components/State";
import { Link, useParams } from "react-router-dom";
import { apiGetBrief } from "../api";
import type { ExperimentBrief } from "../types";

export default function PreMeetingBrief() {
  const { experimentId } = useParams<{ experimentId: string }>();
  const [data, setData] = useState<ExperimentBrief | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!experimentId) return;
    apiGetBrief(experimentId).then(setData).catch((e) => setErr(e.message));
  }, [experimentId]);

  if (err) return <ErrorState message={err} />;
  if (!data) return <Loading />;

  const cc = data.current_claim;
  const pv = cc?.parameter_version;
  const lr = data.last_result;

  return (
    <div className="fade-in">
      <div className="flex justify-between items-end mb-4 flex-wrap gap-3">
        <div className="meta-row">
          <span className="mono">{data.experiment_id}</span>
          <span className="sep" />
          <span>{data.name}</span>
        </div>
        <Link to={`/passport/${data.experiment_id}`} className="btn sm ghost">
          查看实验护照 →
        </Link>
      </div>

      <div className="grid gap-4" style={{ gridTemplateColumns: "1.05fr .95fr" }}>
        <div className="card">
          <div className="section-title">
            <b>只读上下文包</b>
            <span className="tag green">来源已校验</span>
          </div>
          <div className="grid gap-2.5">
            <div className="border border-line rounded-xl p-3.5">
              <b className="text-sm">实验身份</b>
              <p className="mt-1.5 text-muted text-sm leading-relaxed">
                {data.name} · 项目 {data.project_id || "-"} · 状态 {data.status}
              </p>
            </div>
            <div className="border border-line rounded-xl p-3.5">
              <b className="text-sm">当前目标</b>
              <p className="mt-1.5 text-muted text-sm leading-relaxed">
                {data.current_goal || "暂无目标记录（待会议传入）"}
              </p>
            </div>
            <div className="border border-line rounded-xl p-3.5">
              <b className="text-sm flex items-center gap-2">
                当前生效参数
                <span className="tag blue" style={{ padding: "2px 8px", fontSize: 11 }}>
                  v{pv?.version || "无"}
                </span>
              </b>
              {pv?.parameters && pv.parameters.length > 0 ? (
                <div className="mt-2 grid gap-1 text-sm">
                  {pv.parameters.map((p, i) => (
                    <div key={i} className="flex items-baseline gap-1.5">
                      <b className="text-muted text-xs">{p.name}：</b>
                      <span className="font-mono font-semibold">{p.value}</span>
                      <span className="text-xs text-muted">{p.unit}</span>
                    </div>
                  ))}
                  {pv.scope && (
                    <div className="text-xs text-muted mt-1.5">
                      适用范围：{Object.entries(pv.scope).map(([k, v]) => `${k}=${v}`).join(" / ")}
                    </div>
                  )}
                </div>
              ) : (
                <p className="mt-1.5 text-muted text-sm">尚无生效参数（待首次会议确认）</p>
              )}
            </div>
            <div className="border border-line rounded-xl p-3.5">
              <b className="text-sm">上一轮结果</b>
              {lr ? (
                <div className="mt-2 text-sm space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-muted text-xs">结果 ID：</span>
                    <span className="font-mono text-xs">{lr.result_id}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-muted text-xs">知识状态：</span>
                    <span className={`tag ${lr.knowledge_status === "supported" ? "green" : "amber"}`}>
                      {lr.knowledge_status || "-"}
                    </span>
                  </div>
                  {lr.metrics && (
                    <div className="mt-1.5 text-xs flex flex-wrap gap-3">
                      {Object.entries(lr.metrics).map(([k, v]) => (
                        <span key={k}>
                          <b className="text-muted">{k}：</b>
                          {String(v)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <p className="mt-1.5 text-muted text-sm">暂无已发布结果</p>
              )}
            </div>
            <div className="border border-line rounded-xl p-3.5">
              <b className="text-sm">相似失败边界</b>
              {data.failure_boundaries.length > 0 ? (
                <ul className="mt-2 text-sm space-y-1">
                  {data.failure_boundaries.map((fb, i) => (
                    <li key={i} className="text-muted flex items-start gap-2">
                      <span className="text-amber-600 mt-0.5">⚠</span>
                      {(fb as { phenomenon?: string }).phenomenon || JSON.stringify(fb)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1.5 text-muted text-sm">暂无失败边界记录</p>
              )}
            </div>
            <div className="border border-line rounded-xl p-3.5">
              <b className="text-sm">物料与设备</b>
              <p className="mt-1.5 text-muted text-sm leading-relaxed">
                {(data.resources?.note as string) || "简化版未接入物料/设备系统"}
              </p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="section-title">
            <b>AI 建议议程</b>
          </div>
          <ol className="space-y-2.5 text-sm text-slate-700 list-decimal pl-5">
            <li>确认上一轮结果和偏差</li>
            <li>复核当前参数版本与适用范围</li>
            <li>确认是否调整参数或增加对照组</li>
            <li>核对物料批次与设备可用性</li>
            <li>明确实际参数回填与异常登记规则</li>
            <li>确认负责人、截止时间和复盘节点</li>
          </ol>
          <div
            className="mt-4 p-3.5 rounded-xl"
            style={{ background: "var(--amber-soft)", border: "1px solid #f1cf87" }}
          >
            <h3 className="font-bold text-amber-700 text-sm mb-1">待决策问题</h3>
            <p className="text-sm text-amber-800 leading-relaxed">
              {data.pending_questions.length > 0
                ? data.pending_questions.join("；")
                : "本次会议是否需要更新参数版本？是否需要发起复验任务？"}
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-line text-xs text-muted leading-relaxed">
            数据来源：实验当前主张 <span className="font-mono">{cc?.claim_id || "（无）"}</span>
            。由会议候选驱动，参数不硬编码。
          </div>
        </div>
      </div>
    </div>
  );
}
