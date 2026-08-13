import { useEffect, useState } from "react";
import { Loading, ErrorState } from "../components/State";
import { Link, useParams } from "react-router-dom";
import { apiConfirmReview, apiGetMeeting } from "../api";
import { dialog } from "../dialog";
import type { CandidateOut, MeetingDetailOut } from "../types";

export default function DecisionCompiler() {
  const { meetingId } = useParams<{ meetingId: string }>();
  const [data, setData] = useState<MeetingDetailOut | null>(null);
  const [err, setErr] = useState("");
  const [reviewed, setReviewed] = useState(false);

  const load = () => {
    if (!meetingId) return;
    apiGetMeeting(meetingId).then(setData).catch((e) => setErr(e.message));
  };
  useEffect(load, [meetingId]);

  if (err) return <ErrorState message={err} />;
  if (!data) return <Loading />;

  const paramCandidates = data.candidates.filter((c) => c.type === "parameter_change");
  const risks = data.candidates.filter((c) => c.type === "risk");
  const others = data.candidates.filter((c) => c.type !== "parameter_change" && c.type !== "risk");

  const handleQuickConfirm = async () => {
    const ok = await dialog.confirm({
      title: "快速确认",
      message: "确认本次会议决策（不修改）？",
      confirmText: "确认",
    });
    if (!ok) return;
    await apiConfirmReview(meetingId!, { decision: "confirmed" });
    setReviewed(true);
    load();
  };

  return (
    <div className="fade-in">
      <div className="grid gap-4" style={{ gridTemplateColumns: "1.05fr .95fr" }}>
        <div className="card" style={{ maxHeight: 620, overflow: "auto" }}>
          <div className="section-title">
            <b>会议逐字稿</b>
            <span className="section-meta">{data.transcript.length} 段</span>
          </div>
          {data.transcript.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">💬</div>
              <div className="empty-title">暂无逐字稿</div>
            </div>
          ) : (
            data.transcript.map((s, i) => (
              <div key={i} className="speech-bubble">
                <div className="avatar">{s.speaker.slice(0, 1)}</div>
                <div className="flex-1 min-w-0">
                  <small>
                    {String(s.start_offset_sec ?? "")}
                    {s.end_offset_sec ? ` - ${s.end_offset_sec}` : ""} · {s.speaker}
                  </small>
                  <p>{s.text}</p>
                </div>
              </div>
            ))
          )}
          {data.summary && (
            <div className="mt-4 pt-3 border-t border-line text-xs">
              <b className="text-muted">会议摘要：</b>
              {data.summary}
            </div>
          )}
        </div>

        <div>
          <div className="section-title" style={{ marginBottom: 10 }}>
            <b>AI 候选对象（{data.candidates.length}）</b>
          </div>
          {paramCandidates.map((c) => (
            <CandidateCard key={c.candidate_id} c={c} variant="blue" />
          ))}
          {others.map((c) => (
            <CandidateCard key={c.candidate_id} c={c} variant="default" />
          ))}
          {risks.map((c) => (
            <CandidateCard key={c.candidate_id} c={c} variant="risk" />
          ))}
          {data.candidates.length === 0 && (
            <div className="card">
              <div className="empty-state">
                <div className="empty-icon">🤖</div>
                <div className="empty-title">暂无候选对象</div>
                <div className="empty-desc">等待 Aily 编译推送</div>
              </div>
            </div>
          )}

          <div className="card mt-4">
            <div className="section-title">
              <b>复核操作</b>
            </div>
            <p className="text-xs muted -mt-2 mb-3">
              状态：
              <span className={`tag ${data.review?.decision === "confirmed" ? "green" : data.review?.decision === "ended" ? "red" : "blue"}`}>
                {data.review?.status || "pending"}
                {data.review?.decision ? ` · ${data.review.decision}` : ""}
              </span>
            </p>
            <div className="flex gap-2 flex-wrap">
              <button className="btn success" onClick={handleQuickConfirm} disabled={reviewed || data.review?.status === "processed"}>
                {data.review?.decision === "confirmed" ? "已确认" : "确认并生成任务草稿"}
              </button>
              <Link to={`/review/${meetingId}`} className="btn ghost">
                进入复核台修改
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function CandidateCard({ c, variant }: { c: CandidateOut; variant: "blue" | "risk" | "default" }) {
  const borderColor =
    variant === "risk" ? "var(--amber)" : variant === "blue" ? "var(--blue)" : "var(--line)";
  return (
    <div
      className="card mb-3"
      style={{ borderLeft: `4px solid ${borderColor}`, padding: 14 }}
    >
      <h3 className="font-bold text-sm mb-2 flex items-center gap-2 flex-wrap">
        {c.title}
        <span className="text-xs text-muted font-normal">({c.type})</span>
      </h3>
      {c.description && <p className="text-xs text-muted mb-2">{c.description}</p>}
      <div className="grid gap-1.5 text-xs" style={{ gridTemplateColumns: "92px 1fr" }}>
        {c.experiment_ref && (
          <>
            <b className="text-muted">实验编号</b>
            <span className="font-mono">{c.experiment_ref}</span>
          </>
        )}
        {c.confidence !== undefined && c.confidence !== null && (
          <>
            <b className="text-muted">置信度</b>
            <span>{(c.confidence * 100).toFixed(0)}%</span>
          </>
        )}
        {c.parameters.length > 0 && (
          <>
            <b className="text-muted">参数</b>
            <span>
              {c.parameters.map((p, i) => (
                <span key={i} className="mr-2">
                  {p.name}={p.value}
                  {p.unit && <span className="text-muted">{p.unit}</span>}
                </span>
              ))}
            </span>
          </>
        )}
        {c.evidence.length > 0 && (
          <>
            <b className="text-muted">证据</b>
            <span>
              {c.evidence.map((e, i) => (
                <span key={i} className="block">
                  {e.speaker && <b>{e.speaker}：</b>}
                  {e.text}
                </span>
              ))}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
