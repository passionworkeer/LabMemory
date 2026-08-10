import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiPublishResult, apiStartTask, apiSubmitResult } from "../api";
import { dialog } from "../dialog";
import ParameterEditor, { type ParamRow } from "../components/ParameterEditor";
import type { MeetingDetailOut, ResultOut } from "../types";
import { useAuth } from "../store";

export default function ResultBackflow() {
  const { taskId } = useParams<{ taskId: string }>();
  const [meeting, setMeeting] = useState<MeetingDetailOut | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [actualParamRows, setActualParamRows] = useState<ParamRow[]>([]);
  const [metricRows, setMetricRows] = useState<ParamRow[]>([]);
  const [notes, setNotes] = useState("");
  const [publishStatus, setPublishStatus] = useState<"supported" | "partially_supported" | "refuted">("partially_supported");
  const [failurePhenomenon, setFailurePhenomenon] = useState("");
  const [failureTrigger, setFailureTrigger] = useState("");
  const [modelVersion, setModelVersion] = useState("");
  const [modelPrediction, setModelPrediction] = useState("");
  const { user } = useAuth();
  const canPublish = user?.global_role === "pi" || user?.global_role === "lead" || user?.global_role === "admin";

  const load = () => {
    if (!taskId) return;
    fetch("/api/meetings", { headers: { Authorization: `Bearer ${localStorage.getItem("labmemory_token")}` } })
      .then((r) => r.json())
      .then((ms: MeetingDetailOut[]) => {
        const m = ms.find((x) => x.task?.task_id === taskId);
        if (m) {
          setMeeting(m);
          const pp = m.task?.planned_params as { parameters?: { name: string; value: string; unit?: string }[] } | null;
          if (pp?.parameters) {
            setActualParamRows(
              pp.parameters.map((p) => ({
                name: p.name,
                value: String(p.value ?? ""),
                unit: p.unit ?? "",
              }))
            );
          }
        }
      })
      .catch((e) => setErr(e.message));
  };
  useEffect(load, [taskId]);

  const submitResult = async () => {
    setBusy(true);
    try {
      const rowsToDict = (rows: ParamRow[]) =>
        rows.filter((r) => r.name.trim()).map((r) => [r.name.trim(), r.value]);
      const ap = Object.fromEntries(rowsToDict(actualParamRows));
      const mt = Object.fromEntries(rowsToDict(metricRows));
      const r = await apiSubmitResult(taskId!, {
        actual_params: Object.keys(ap).length > 0 ? ap : undefined,
        metrics: Object.keys(mt).length > 0 ? mt : undefined,
        notes: notes || undefined,
      });
      await dialog.alert({
        message: `结果已提交（${r.status}）`,
        variant: r.status === "frozen" ? "warning" : "success",
      });
      load();
    } catch (e) {
      await dialog.alert({ message: "提交失败：" + (e as Error).message, variant: "error" });
    } finally {
      setBusy(false);
    }
  };

  const startTask = async () => {
    setBusy(true);
    try {
      await apiStartTask(taskId!);
      load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const publish = async (r: ResultOut) => {
    if (!canPublish) {
      await dialog.alert({ message: "仅 PI / Lead 可发布知识", variant: "warning" });
      return;
    }
    setBusy(true);
    try {
      await apiPublishResult(r.result_id, {
        knowledge_status: publishStatus,
        notes: notes || undefined,
        failure_boundary:
          failurePhenomenon || failureTrigger
            ? {
                phenomenon: failurePhenomenon,
                trigger_condition: failureTrigger,
                ruled_out: "物料批次、仪器校准",
                root_cause_status: "待验证",
                next_step: "调整参数复验",
              }
            : undefined,
        model_feedback: modelVersion
          ? {
              model_version: modelVersion,
              prediction: modelPrediction,
              actual: JSON.stringify(r.metrics),
              deviation_type: "待算法组确认",
              feedback_task: "纳入候选训练样本",
            }
          : undefined,
      });
      await dialog.alert({
        message: "结果已发布为知识，主张 knowledge_status 已更新",
        variant: "success",
      });
      load();
    } catch (e) {
      await dialog.alert({ message: "发布失败：" + (e as Error).message, variant: "error" });
    } finally {
      setBusy(false);
    }
  };

  if (err && !meeting) return <div className="text-red-500">{err}</div>;
  if (!meeting) return <div className="text-slate-400">加载中...</div>;

  const task = meeting.task;
  const audit = meeting.audit;
  const results = meeting.results;
  const planned = (task?.planned_params as { parameters?: { name: string; value: string; unit?: string }[] }) || {};

  return (
    <div className="fade-in">
      <div className="flex justify-between items-end mb-4 flex-wrap gap-3">
        <div className="meta-row">
          <span className="mono">任务 {task?.task_id}</span>
          {task && (
            <>
              <span className="sep" />
              <span>状态：{task.status}</span>
            </>
          )}
        </div>
        <Link to={`/passport/${meeting.experiment_id}`} className="btn sm ghost">
          实验护照 →
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4 max-md:grid-cols-1">
        <div className="card">
          <div className="section-title">
            <b>计划参数（来自主张版本）</b>
          </div>
          {planned.parameters && planned.parameters.length > 0 ? (
            <div className="space-y-2">
              {planned.parameters.map((p, i) => (
                <div key={i} className="flex justify-between items-end pb-2 border-b border-line-light last:border-0">
                  <div>
                    <small className="text-muted">{p.name}</small>
                    <strong className="block text-xl">
                      {p.value} {p.unit}
                    </strong>
                  </div>
                  <span className="tag blue">计划</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted text-sm">无计划参数</p>
          )}
        </div>

        <div className="card">
          <div className="section-title">
            <b>任务执行控制</b>
          </div>
          <div className="text-sm space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="muted">审计状态</span>
              <span className={`tag ${audit?.status === "passed" ? "green" : audit?.status === "blocked" ? "red" : "amber"}`}>
                {audit?.status || "未审计"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="muted">任务状态</span>
              <span className={`tag ${task?.status === "completed" ? "green" : "blue"}`}>{task?.status}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="muted">结果提交</span>
              <span className={`tag ${results.length > 0 ? "green" : "gray"}`}>
                {results.length > 0 ? `已提交 ${results.length} 条` : "未提交"}
              </span>
            </div>
          </div>
          <div className="mt-4 flex gap-2 flex-wrap">
            {task?.status === "draft" && audit?.status === "passed" && (
              <button className="btn success" onClick={startTask} disabled={busy}>
                启动任务
              </button>
            )}
            {task?.status === "running" && (
              <p className="text-xs muted leading-relaxed">
                任务运行中。提交实验结果后将自动标记为已完成，无需单独操作。
              </p>
            )}
            {task?.status === "completed" && results.length > 0 && (
              <p className="text-xs muted leading-relaxed">
                任务已完成，结果已提交。每个任务仅可提交一次结果。
              </p>
            )}
          </div>
        </div>
      </div>

      {/* 提交结果区：仅在无已提交结果且任务处于可提交状态时显示 */}
      {(task?.status === "running" || (task?.status === "completed" && results.length === 0)) && (
        <div className="card mb-4">
          <div className="section-title">
            <b>提交实验结果</b>
            <span className="section-meta">PI / Lead / Executor 均可提交 · 每个任务仅可提交一次</span>
          </div>
          <p className="text-xs muted -mt-2 mb-3">
            提交后任务将自动标记为已完成；实际参数与计划参数 key 不一致会触发 frozen。
          </p>
          <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <div className="field">
              <label className="field-label">实际参数（可修改）</label>
              <ParameterEditor
                rows={actualParamRows}
                onChange={setActualParamRows}
                mode="kv"
                namePlaceholder="参数名"
                valuePlaceholder="实际值"
              />
            </div>
            <div className="field">
              <label className="field-label">指标（如转化率/副产物）</label>
              <ParameterEditor
                rows={metricRows}
                onChange={setMetricRows}
                mode="kv"
                namePlaceholder="指标名"
                valuePlaceholder="数值"
                emptyHint="暂无指标，点击下方「+ 添加」录入，如转化率 / 副产物"
              />
            </div>
          </div>
          <div className="mt-3 field">
            <label className="field-label">备注</label>
            <input
              className="input"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="结果说明、偏差原因等"
            />
          </div>
          <div className="mt-4 flex justify-end">
            <button className="btn primary" onClick={submitResult} disabled={busy}>
              {busy ? "提交中..." : "提交结果"}
            </button>
          </div>
        </div>
      )}

      {results.length > 0 && (
        <div className="card mb-4">
          <div className="section-title">
            <b>结果列表</b>
            <span className="section-meta">{results.length} 条</span>
          </div>
          <div className="space-y-3">
            {results.map((r) => (
              <div key={r.result_id} className="border border-line rounded-xl p-3">
                <div className="flex justify-between items-start flex-wrap gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-sm flex items-center gap-2 flex-wrap">
                      <span className="mono">{r.result_id}</span>
                      <span className={`tag ${r.status === "published" ? "green" : r.status === "frozen" ? "red" : "blue"}`}>
                        {r.status}
                      </span>
                      {r.knowledge_status && (
                        <span className={`tag ${r.knowledge_status === "supported" ? "green" : "amber"}`}>
                          {r.knowledge_status}
                        </span>
                      )}
                    </div>
                    <div className="text-xs muted mt-1.5">
                      实际参数：{JSON.stringify(r.actual_params)} · 指标：{JSON.stringify(r.metrics)}
                    </div>
                  </div>
                  {r.status === "submitted" && canPublish && (
                    <button className="btn success sm" onClick={() => publish(r)} disabled={busy}>
                      发布为知识
                    </button>
                  )}
                  {r.status === "submitted" && !canPublish && (
                    <span className="text-xs muted">仅 PI/Lead 可发布</span>
                  )}
                </div>
                {r.failure_boundary && (
                  <div className="mt-2 p-2.5 rounded-lg text-xs" style={{ background: "#fffafb", border: "1px solid #f0c6c9" }}>
                    <b className="text-red-700">失败边界卡：</b>
                    {r.failure_boundary.phenomenon} · 触发 {r.failure_boundary.trigger_condition} · 根因{" "}
                    {r.failure_boundary.root_cause_status}
                  </div>
                )}
                {r.model_feedback && (
                  <div className="mt-1.5 p-2.5 rounded-lg text-xs" style={{ background: "var(--purple-soft)" }}>
                    <b className="text-purple-700">模型偏差卡：</b>
                    模型 {r.model_feedback.model_version} · 预测 {r.model_feedback.prediction} · 偏差{" "}
                    {r.model_feedback.deviation_type}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {canPublish && results.some((r) => r.status === "submitted") && (
        <div className="card">
          <div className="section-title">
            <b>发布知识时填写失败边界 / 模型偏差</b>
            <span className="section-meta">可选</span>
          </div>
          <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <div className="field">
              <label className="field-label">知识状态</label>
              <select
                className="input"
                value={publishStatus}
                onChange={(e) => setPublishStatus(e.target.value as "supported" | "partially_supported" | "refuted")}
              >
                <option value="supported">supported（支持）</option>
                <option value="partially_supported">partially_supported（部分支持）</option>
                <option value="refuted">refuted（推翻）</option>
              </select>
            </div>
            <div className="field">
              <label className="field-label">失败现象</label>
              <input
                className="input"
                value={failurePhenomenon}
                onChange={(e) => setFailurePhenomenon(e.target.value)}
                placeholder="如：副产物升至 9%"
              />
            </div>
            <div className="field">
              <label className="field-label">触发条件</label>
              <input
                className="input"
                value={failureTrigger}
                onChange={(e) => setFailureTrigger(e.target.value)}
                placeholder="如：65℃ / 2h / 1.0 eq"
              />
            </div>
            <div className="field">
              <label className="field-label">模型版本</label>
              <input
                className="input mono"
                value={modelVersion}
                onChange={(e) => setModelVersion(e.target.value)}
                placeholder="如：MODEL-RXN-v7"
              />
            </div>
            <div className="field col-span-2 max-md:col-span-1">
              <label className="field-label">模型预测</label>
              <input
                className="input"
                value={modelPrediction}
                onChange={(e) => setModelPrediction(e.target.value)}
                placeholder="如：成功率 86%，副产物 ≤5%"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
