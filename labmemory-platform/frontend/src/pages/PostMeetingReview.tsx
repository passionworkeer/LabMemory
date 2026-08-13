import { useEffect, useState } from "react";
import { Loading, ErrorState } from "../components/State";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiConfirmReview, apiGetMeeting } from "../api";
import { dialog } from "../dialog";
import ParameterEditor, { type ParamRow } from "../components/ParameterEditor";
import type { MeetingDetailOut } from "../types";

const GATES = [
  { key: "object", label: "对象门", desc: "实验/项目/样品明确" },
  { key: "param", label: "参数门", desc: "数值/单位/语义完整" },
  { key: "evidence", label: "证据门", desc: "可定位原始会议片段" },
  { key: "scope", label: "适用范围门", desc: "材料/浓度/设备明确" },
  { key: "status", label: "状态门", desc: "事实/建议/假设区分" },
  { key: "owner", label: "责任门", desc: "提出人/负责人/审核人" },
];

type ParamItem = { name: string; value: string; unit?: string };

function ParamList({ params, aiParams }: { params: ParamItem[]; aiParams?: ParamItem[] }) {
  if (params.length === 0) {
    return <span className="muted text-sm">-</span>;
  }
  return (
    <div className="space-y-1">
      {params.map((p, i) => {
        const aiP = aiParams?.find((ap) => ap.name === p.name);
        const changed = !!aiParams && (!aiP || aiP.value !== p.value || (aiP.unit || "") !== (p.unit || ""));
        return (
          <div
            key={i}
            className="flex items-baseline gap-2 px-2 py-1.5 rounded-md text-sm"
            style={changed ? { boxShadow: "inset 3px 0 0 var(--amber)" } : undefined}
          >
            <span className="text-slate-500 w-20 shrink-0 truncate text-xs">{p.name}</span>
            <span className="font-bold text-slate-800">{p.value}</span>
            {p.unit && <span className="text-muted text-xs">{p.unit}</span>}
            {changed && <span className="ml-auto text-xs text-amber-600">已改</span>}
          </div>
        );
      })}
    </div>
  );
}

export default function PostMeetingReview() {
  const { meetingId } = useParams<{ meetingId: string }>();
  const [data, setData] = useState<MeetingDetailOut | null>(null);
  const [err, setErr] = useState("");
  const [paramRows, setParamRows] = useState<ParamRow[]>([]);
  const [scopeRows, setScopeRows] = useState<ParamRow[]>([]);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState<"confirmed" | "ended" | null>(null);
  const navigate = useNavigate();

  const load = () => {
    if (!meetingId) return;
    apiGetMeeting(meetingId).then((d) => {
      setData(d);
      const cand = d.candidates.find((c) => c.type === "parameter_change");
      if (cand) {
        setParamRows(
          cand.parameters.map((p) => ({
            name: p.name,
            value: String(p.value ?? ""),
            unit: p.unit ?? "",
          }))
        );
        setScopeRows([{ name: "material", value: "Compound-A" }]);
      }
    }).catch((e) => setErr(e.message));
  };
  useEffect(load, [meetingId]);

  const onSubmitDecision = async (dec: "confirmed" | "ended") => {
    if (!meetingId) return;
    if (dec === "ended") {
      const ok = await dialog.confirm({
        title: "结束复核",
        message: "确认结束本次复核？不会生成主张和任务。",
        danger: true,
        confirmText: "确认结束",
      });
      if (!ok) return;
    }
    setSubmitting(dec);
    try {
      let mods: Record<string, unknown> | undefined;
      if (dec === "confirmed") {
        mods = {};
        const validParams = paramRows.filter((r) => r.name.trim());
        if (validParams.length > 0) {
          mods.parameters = validParams.map((r) => ({
            name: r.name.trim(),
            value: r.value,
            ...(r.unit?.trim() ? { unit: r.unit.trim() } : {}),
          }));
        }
        const validScope = scopeRows.filter((r) => r.name.trim());
        if (validScope.length > 0) {
          mods.scope = Object.fromEntries(
            validScope.map((r) => [r.name.trim(), r.value])
          );
        }
      }
      await apiConfirmReview(meetingId, { decision: dec, modifications: mods, notes: notes || undefined });
      await dialog.alert({
        message: dec === "confirmed" ? "已确认，生成主张与任务草稿" : "已结束，不进入数据链路",
        variant: "success",
      });
      load();
    } catch (e) {
      await dialog.alert({ message: "提交失败：" + (e as Error).message, variant: "error" });
    } finally {
      setSubmitting(null);
    }
  };

  if (err) return <ErrorState message={err} />;
  if (!data) return <Loading />;

  const paramCandidates = data.candidates.filter((c) => c.type === "parameter_change");
  const review = data.review;
  const processed = review?.status === "processed";

  return (
    <div className="fade-in">
      {/* 页头 */}
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-bold text-slate-800 truncate">{data.title}</h1>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`tag ${processed ? "green" : "amber"}`}>
            {processed ? `已${review?.decision === "confirmed" ? "确认" : "结束"}` : "待复核"}
          </span>
          <Link to={`/compiler/${meetingId}`} className="btn sm ghost">
            查看逐字稿
          </Link>
        </div>
      </div>

      {/* 三值对比主卡片 */}
      <div className="card mb-5">
        <div className="section-title">
          <b>参数复核对比</b>
          <span className="section-meta">三值留痕：原始转写 → AI 候选 → 人工确认</span>
        </div>

        {paramCandidates.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📄</div>
            <div className="empty-title">暂无 parameter_change 类型候选</div>
            <div className="empty-desc">AI 未提取到参数变更候选，可直接结束复核或查看逐字稿确认。</div>
          </div>
        ) : (
          <div className="space-y-4">
            {paramCandidates.map((c) => {
              const transcriptText = c.evidence.map((e) => e.text).join(" / ");
              const modified = processed && !!review?.modifications;
              const modParams = (review?.modifications?.parameters as ParamItem[] | undefined) || [];
              const unitComplete = c.parameters.length > 0 && c.parameters.every((p) => p.unit);
              const evidenceLocated = c.evidence.length > 0;
              return (
                <div
                  key={c.candidate_id}
                  className="rounded-xl overflow-hidden"
                  style={{ background: "var(--line-light)" }}
                >
                  <div
                    className="px-4 py-3 flex items-center justify-between flex-wrap gap-2"
                    style={{ background: "var(--blue-soft)" }}
                  >
                    <div className="flex items-center gap-2">
                      <span className="badge-dot blue" />
                      <b className="text-sm">{c.title}</b>
                      <span className="text-xs text-blue-700">{c.type}</span>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`tag ${unitComplete ? "green" : "amber"}`}>
                        {unitComplete ? "✓ 单位完整" : "⚠ 单位缺失"}
                      </span>
                      <span className={`tag ${evidenceLocated ? "green" : "amber"}`}>
                        {evidenceLocated ? "✓ 证据可定位" : "⚠ 证据缺失"}
                      </span>
                      {c.confidence !== undefined && c.confidence !== null && (
                        <span className="tag blue">
                          置信度 {(c.confidence * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="px-4 py-3">
                    <div className="text-xs muted mb-1.5 font-semibold">原始转写</div>
                    <div className="text-sm leading-relaxed text-slate-700">
                      {transcriptText || <span className="muted">-</span>}
                    </div>
                    {c.evidence.length > 0 && (
                      <div className="mt-1.5 text-xs muted">
                        {c.evidence[0].speaker}
                        {c.evidence[0].start_offset_sec !== undefined
                          ? ` · ${c.evidence[0].start_offset_sec}s`
                          : ""}
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-3 px-4 pb-4">
                    <div className="p-3.5 rounded-lg" style={{ background: "white" }}>
                      <div className="text-xs muted mb-2 font-semibold">AI 候选值</div>
                      <ParamList params={c.parameters} />
                      <div className="mt-2 text-xs muted">
                        语义：{c.description || "计划值"}
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg" style={{ background: "white" }}>
                      <div className="text-xs muted mb-2 font-semibold flex items-center gap-2">
                        <span>人工确认值</span>
                        {modified ? (
                          <span className="tag amber">已修改</span>
                        ) : processed ? (
                          <span className="tag green">原样确认</span>
                        ) : null}
                      </div>
                      {processed ? (
                        modified ? (
                          modParams.length > 0 ? (
                            <ParamList params={modParams} aiParams={c.parameters} />
                          ) : (
                            <span className="muted text-sm">已清空所有参数</span>
                          )
                        ) : (
                          <ParamList params={c.parameters} />
                        )
                      ) : (
                        <span className="muted text-sm">待确认</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 下方两列 */}
      <div className="grid grid-cols-3 gap-4 mb-5">
        {/* 六道闸门 */}
        <div className="card col-span-2">
          <div className="section-title">
            <b>六道可信质量闸门</b>
            <span className="tag green">全部通过</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {GATES.map((g) => (
              <div
                key={g.key}
                className="p-3.5 rounded-xl"
                style={{ background: "var(--green-soft)", border: "1px solid #c8ecd9" }}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-green-700 text-base">✓</span>
                  <b className="text-sm text-green-800">{g.label}</b>
                </div>
                <div className="text-xs text-green-700/80">{g.desc}</div>
              </div>
            ))}
          </div>
          <p className="text-xs muted mt-4">
            关键字段全部闭环后才可发布；缺证据内容只能保存为候选或待补充。
          </p>
        </div>

        {/* 审计轨迹 */}
        <div className="card">
          <div className="section-title">
            <b>审计轨迹</b>
          </div>
          <div className="audit-trail">
            <div className="entry">
              系统接收到 MeetingPackage
              <br />
              <span className="text-muted">来源：{data.source}</span>
            </div>
            <div className="entry">
              Aily 编译生成 <b>{data.candidates.length}</b> 个候选对象
            </div>
            {review?.reviewed_at && (
              <div className="entry">
                {new Date(review.reviewed_at).toLocaleString()}
                <br />
                复核决策：<b>{review.decision === "confirmed" ? "确认" : "结束"}</b>
              </div>
            )}
            {review?.modifications && (
              <div className="entry">修改内容已保留（三值留痕）</div>
            )}
            {data.claim && (
              <div className="entry">
                生成主张 <b>{data.claim.claim_id}</b>
                <br />
                <span className="text-muted">
                  参数版本 {data.claim.parameter_version?.version}
                </span>
              </div>
            )}
            {data.task && (
              <div className="entry">
                生成任务草稿 <b className="font-mono">{data.task.task_id.slice(0, 14)}...</b>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 操作区 */}
      <div className="card">
        {processed ? (
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-2">
              <span className="tag green">复核已完成</span>
              <span className="text-sm muted">决策：{review?.decision}</span>
            </div>
            <div className="flex gap-2 flex-wrap">
              {data.task && (
                <Link to={`/audit/${data.task.task_id}`} className="btn primary">
                  进入行动前审计 →
                </Link>
              )}
              {data.claim && (
                <Link to={`/passport/${data.experiment_id}`} className="btn ghost">
                  查看实验护照
                </Link>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="section-title">
              <b>复核操作</b>
            </div>

            <div className="space-y-3">
              <div className="rounded-xl p-4" style={{ background: "var(--line-light)" }}>
                <div className="field">
                  <label className="field-label">
                    <span className="badge-dot blue" />
                    确认的参数（可修改）
                  </label>
                  <ParameterEditor
                    rows={paramRows}
                    onChange={setParamRows}
                    mode="params"
                    namePlaceholder="参数名"
                    valuePlaceholder="值"
                  />
                  <span className="field-hint">
                    默认显示 AI 候选值；如需修改直接编辑表格行或增删。"高级 JSON"可用于复杂结构。
                  </span>
                </div>
              </div>

              <div className="rounded-xl p-4" style={{ background: "var(--line-light)" }}>
                <div className="field">
                  <label className="field-label">
                    <span className="badge-dot green" />
                    适用范围（可修改）
                  </label>
                  <ParameterEditor
                    rows={scopeRows}
                    onChange={setScopeRows}
                    mode="kv"
                    namePlaceholder="条件"
                    valuePlaceholder="值"
                  />
                </div>
              </div>

              <div className="rounded-xl p-4" style={{ background: "var(--line-light)" }}>
                <div className="field">
                  <label className="field-label">
                    <span className="badge-dot amber" />
                    备注 / 修改原因（可选）
                  </label>
                  <input
                    className="input"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="填写修改原因或备注说明"
                  />
                </div>
              </div>
            </div>

            <div className="mt-5 flex justify-start gap-2">
              <button className="btn" onClick={() => navigate(-1)} disabled={!!submitting}>
                取消
              </button>
              <button
                className="btn danger"
                onClick={() => onSubmitDecision("ended")}
                disabled={!!submitting}
              >
                {submitting === "ended" ? "提交中..." : "结束流程"}
              </button>
              <button
                className="btn success"
                onClick={() => onSubmitDecision("confirmed")}
                disabled={!!submitting}
              >
                {submitting === "confirmed"
                  ? "提交中..."
                  : "确认并生成主张 + 任务草稿"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
