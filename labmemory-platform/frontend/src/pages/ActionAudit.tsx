import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  apiAckFailureBoundary,
  apiApproveTask,
  apiAuditCompare,
  apiAuditFix,
  apiRejectTask,
  apiRunAudit,
  apiStartTask,
  apiUpdateResources,
} from "../api";
import { dialog } from "../dialog";
import ParameterEditor, { type ParamRow } from "../components/ParameterEditor";
import type { ActionAuditOut, AuditCompareOut } from "../types";
import { useAuth } from "../store";

type CheckStatus = "passed" | "needs_confirmation" | "blocked" | "pending";

const CHECK_LABELS: Record<string, string> = {
  version_unit: "版本与单位",
  evidence_scope: "证据与范围",
  approval: "审批状态",
  resource: "物料设备",
  failure_boundary: "失败边界",
};

interface FailureBoundaryItem {
  result_id: string;
  task_id: string;
  phenomenon?: string;
  trigger_condition?: string;
  root_cause_status?: string;
  next_step?: string;
}

export default function ActionAudit() {
  const { taskId } = useParams<{ taskId: string }>();
  const [compare, setCompare] = useState<AuditCompareOut | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [resourceModalOpen, setResourceModalOpen] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();
  const canApprove = user?.global_role === "pi" || user?.global_role === "lead" || user?.global_role === "admin";

  const load = () => {
    if (!taskId) return;
    setErr("");
    apiAuditCompare(taskId)
      .then(setCompare)
      .catch((e) => setErr(e.message));
  };
  useEffect(load, [taskId]);

  const runAudit = async () => {
    setBusy(true);
    try {
      await apiRunAudit(taskId!);
      load();
    } catch (e) {
      setErr((e as Error).message);
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

  const fixTask = async () => {
    const ok = await dialog.confirm({
      title: "一键修正",
      message: "确认用当前参数版本替换任务绑定的旧版本？将生成新任务草稿。",
      danger: true,
      confirmText: "确认修正",
    });
    if (!ok) return;
    setBusy(true);
    try {
      const newTask = await apiAuditFix(taskId!);
      await dialog.alert({ message: "已生成新任务草稿（绑定当前主张版本）", variant: "success" });
      navigate(`/audit/${newTask.task_id}`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const approveTask = async () => {
    if (!canApprove) {
      await dialog.alert({ message: "仅 PI / Lead 可审批任务", variant: "warning" });
      return;
    }
    const ok = await dialog.confirm({
      title: "审批通过",
      message: "确认批准该任务执行？审批后将更新到审计检查中。",
      confirmText: "审批通过",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await apiApproveTask(taskId!);
      await dialog.alert({ message: "任务已审批通过，请重新审计", variant: "success" });
      load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const rejectTask = async () => {
    if (!canApprove) {
      await dialog.alert({ message: "仅 PI / Lead 可审批任务", variant: "warning" });
      return;
    }
    const ok = await dialog.confirm({
      title: "拒绝审批",
      message: "确认拒绝该任务？任务将被标记为 blocked。",
      danger: true,
      confirmText: "拒绝任务",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await apiRejectTask(taskId!, "已被审批人拒绝");
      await dialog.alert({ message: "任务已拒绝，保持 blocked 状态", variant: "warning" });
      load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const saveResources = async (payload: Parameters<typeof apiUpdateResources>[1]) => {
    setBusy(true);
    try {
      await apiUpdateResources(taskId!, payload);
      setResourceModalOpen(false);
      await dialog.alert({ message: "资源已补充，请重新审计", variant: "success" });
      load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ackFailureBoundary = async () => {
    const ok = await dialog.confirm({
      title: "确认失败边界风险",
      message: "你已了解历史失败边界？确认知晓后失败边界检查将放行。",
      confirmText: "确认知晓",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await apiAckFailureBoundary(taskId!);
      await dialog.alert({ message: "已确认，请重新审计", variant: "success" });
      load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (err && !compare) return <div className="text-red-500">{err}</div>;
  if (!compare) return <div className="text-slate-400">加载中...</div>;

  const audit = compare.audit as ActionAuditOut | null | undefined;
  const task = compare.task;
  // 版本替代阻断：仅在「已执行审计且审计结论 blocked」且任务未启动时展示；
  // 未审计任务保持待审计，不预判阻断；running/completed 已在执行，不受版本变更影响
  const versionBlocked =
    !!audit &&
    audit.status === "blocked" &&
    compare.is_blocked &&
    task?.status !== "running" &&
    task?.status !== "completed";
  const effectiveBlocked = versionBlocked || audit?.status === "blocked";
  const needsConfirm = audit?.status === "needs_confirmation";
  const auditPassed = audit?.status === "passed";
  const canStart = auditPassed && (task?.status === "audited" || task?.status === "draft");

  // 五项检查状态：审计后从 checks 读取，未审计显示待审计
  const checksRaw = (audit?.checks || {}) as Record<string, { status?: string; reason?: string }>;
  const checkStatus = (key: string): CheckStatus => {
    if (!audit) return "pending";
    return (checksRaw[key]?.status as CheckStatus) || "pending";
  };
  const checkReason = (key: string, fallback: string) =>
    !audit ? fallback : checksRaw[key]?.reason || fallback;

  const confirmations = audit?.result?.confirmations || [];
  const failureBoundaries = (checksRaw["failure_boundary"] as unknown as { boundaries?: FailureBoundaryItem[] })?.boundaries || [];

  const statusTag = effectiveBlocked
    ? { label: "已阻断", cls: "red" }
    : auditPassed
    ? { label: "已通过", cls: "green" }
    : needsConfirm
    ? { label: "需确认", cls: "amber" }
    : { label: "待审计", cls: "amber" };

  return (
    <div className="fade-in">
      {/* 顶部状态条 */}
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="meta-row">
          <span className="mono">任务 {compare.task_id}</span>
          {task && (
            <>
              <span className="sep" />
              <span>状态：{task.status}</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`tag ${statusTag.cls}`}>{statusTag.label}</span>
          {(task?.status === "running" || task?.status === "completed") && (
            <Link to={`/result/${task.task_id}`} className="btn sm ghost">
              结果回流 →
            </Link>
          )}
        </div>
      </div>

      {/* 阻断警告条 */}
      {effectiveBlocked && (
        <div
          className="rounded-2xl p-5 mb-5"
          style={{
            background: "linear-gradient(135deg, #fff0f1 0%, #fde6e8 100%)",
            border: "1px solid #f3b5b8",
          }}
        >
          <div className="flex items-start gap-3">
            <div
              className="w-11 h-11 rounded-xl grid place-items-center text-xl flex-shrink-0"
              style={{ background: "var(--red)", color: "white" }}
            >
              ⚠
            </div>
            <div>
              <h2 className="text-lg font-bold text-red-800 mb-1">
                任务已阻断{versionBlocked ? "：引用了过期参数版本" : ""}
              </h2>
              <p className="text-sm text-red-700/80 leading-relaxed">
                {versionBlocked ? (
                  <>
                    任务绑定的主张 {compare.old_claim?.claim_id}（v{compare.old_claim?.parameter_version?.version}）已被新主张{" "}
                    {compare.current_claim?.claim_id}（v{compare.current_claim?.parameter_version?.version}）替代。
                    系统不会静默改写任务，而是展示证据、影响范围和负责人后等待确认。
                  </>
                ) : (
                  <>
                    存在高风险检查未通过（如审批被拒绝、缺少证据），任务不可进入执行。请处理风险后重新审计。
                  </>
                )}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 需确认警告条 */}
      {needsConfirm && !effectiveBlocked && (
        <div
          className="rounded-2xl p-5 mb-5"
          style={{
            background: "linear-gradient(135deg, #fff9ec 0%, #fff3d9 100%)",
            border: "1px solid #f0d9a8",
          }}
        >
          <div className="flex items-start gap-3">
            <div
              className="w-11 h-11 rounded-xl grid place-items-center text-xl flex-shrink-0"
              style={{ background: "var(--amber)", color: "white" }}
            >
              ✋
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-bold text-amber-800 mb-1">审计需要人工确认</h2>
              <ul className="text-sm text-amber-800/80 leading-relaxed space-y-1 mt-2">
                {confirmations.map((c, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1 w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                    {c}
                  </li>
                ))}
              </ul>
              <p className="text-xs mt-3 text-amber-700/70">
                在下方完成审批、补充资源或确认失败边界后，点击「重新审计」。
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 五项检查 */}
      <div className="section-header">
        <div>
          <h2>五项审计检查</h2>
          <p>在任务执行前逐项验证版本、证据、审批、资源和失败边界</p>
        </div>
      </div>
      <div className="grid grid-cols-5 gap-3 mb-5 max-md:grid-cols-2">
        {Object.keys(CHECK_LABELS).map((key) => (
          <CheckCard
            key={key}
            label={CHECK_LABELS[key]}
            status={checkStatus(key)}
            detail={checkReason(key, "待审计")}
          />
        ))}
      </div>

      {/* 待确认事项操作区：需确认或审批被拒（非版本替代阻断）时展示 */}
      {(needsConfirm || task?.approval_status === "rejected") && !versionBlocked && (
        <div className="grid grid-cols-2 gap-4 mb-5 max-md:grid-cols-1">
          {/* 审批门 */}
          <div className="card">
            <div className="section-title">
              <b>审批状态</b>
              <ApprovalTag status={task?.approval_status} />
            </div>
            {task?.approval_status === "approved" ? (
              <p className="text-sm text-green-700">
                已由负责人审批通过{task.approval_note ? `：${task.approval_note}` : ""}
              </p>
            ) : task?.approval_status === "rejected" ? (
              <div>
                <p className="text-sm text-red-700 mb-3">
                  任务已被拒绝审批{task.approval_note ? `：${task.approval_note}` : ""}，可重新审批后再次审计。
                </p>
                {canApprove ? (
                  <button className="btn success sm" onClick={approveTask} disabled={busy}>
                    ✓ 重新审批通过
                  </button>
                ) : (
                  <span className="text-xs muted">仅 PI / Lead 可审批</span>
                )}
              </div>
            ) : (
              <>
                <p className="text-xs muted mb-3">任务尚未审批，需 PI / Lead 确认后方可进入执行。</p>
                <div className="flex gap-2 flex-wrap">
                  {canApprove ? (
                    <>
                      <button className="btn success sm" onClick={approveTask} disabled={busy}>
                        ✓ 审批通过
                      </button>
                      <button className="btn danger sm" onClick={rejectTask} disabled={busy}>
                        拒绝
                      </button>
                    </>
                  ) : (
                    <span className="text-xs muted">仅 PI / Lead 可审批</span>
                  )}
                </div>
              </>
            )}
          </div>

          {/* 资源门 */}
          <div className="card">
            <div className="section-title">
              <b>物料设备与排期</b>
              <span className={`tag ${task?.resource_status === "ready" ? "green" : "amber"}`}>
                {task?.resource_status === "ready" ? "已就绪" : "未确认"}
              </span>
            </div>
            {task?.resource_status === "ready" ? (
              <ResourceSummary resources={task.resources} />
            ) : (
              <>
                <p className="text-xs muted mb-3">补充物料 / 设备 / 排期信息，确认资源可用。</p>
                <button className="btn primary sm" onClick={() => setResourceModalOpen(true)} disabled={busy}>
                  补充资源
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* 失败边界命中展示 */}
      {failureBoundaries.length > 0 && (
        <div className="card mb-5">
          <div className="section-title">
            <b>历史失败边界命中</b>
            <span className={`tag ${task?.failure_boundary_ack ? "green" : "amber"}`}>
              {task?.failure_boundary_ack ? "已确认" : "待确认"}
            </span>
          </div>
          <div className="space-y-2.5 mb-4">
            {failureBoundaries.map((b) => (
              <div
                key={b.result_id}
                className="p-3 rounded-xl text-xs"
                style={{ background: "#fffafb", border: "1px solid #f0c6c9" }}
              >
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <b className="text-red-700">失败边界卡</b>
                  <span className="text-slate-400 font-mono">{b.result_id}</span>
                  <span className="tag red" style={{ padding: "1px 8px" }}>{b.root_cause_status || "待验证"}</span>
                </div>
                <div className="text-slate-600 leading-relaxed">
                  现象：{b.phenomenon || "-"} · 触发：{b.trigger_condition || "-"}
                  {b.next_step ? ` · 下一步：${b.next_step}` : ""}
                </div>
              </div>
            ))}
          </div>
          {!task?.failure_boundary_ack ? (
            <button className="btn ghost-amber sm" onClick={ackFailureBoundary} disabled={busy}>
              确认知晓风险并继续
            </button>
          ) : (
            <p className="text-xs text-green-700">已确认知晓历史失败边界，检查放行。</p>
          )}
        </div>
      )}

      {/* 版本对比：仅版本替代（引用过期参数版本）导致的阻断才展示 */}
      {versionBlocked && compare.old_claim && compare.current_claim && (
        <div className="card mb-5">
          <div className="section-title">
            <b>版本对比：旧主张 vs 当前主张</b>
            <span className="section-meta">一键修正后，旧任务标记为 blocked 并保留审计记录</span>
          </div>
          <div className="grid gap-3 items-stretch" style={{ gridTemplateColumns: "1fr 56px 1fr" }}>
            <VersionCard
              variant="old"
              tagLabel={`旧版本 · ${compare.old_claim.status}`}
              claim={compare.old_claim}
            />
            <div className="flex flex-col items-center justify-center gap-2">
              <div
                className="w-10 h-10 rounded-full grid place-items-center"
                style={{ background: "var(--blue-soft)", color: "var(--blue)" }}
              >
                →
              </div>
              <span className="text-xs muted text-center">替代</span>
            </div>
            <VersionCard
              variant="current"
              tagLabel="当前有效"
              claim={compare.current_claim}
            />
          </div>
        </div>
      )}

      {/* 操作 + 影响 */}
      <div className="grid grid-cols-2 gap-4 mb-5 max-md:grid-cols-1">
        <div className="card">
          <div className="section-title">
            <b>操作</b>
            <span className="section-meta">PI / Lead / Executor 均可执行</span>
          </div>
          <div className="flex gap-2 flex-wrap">
            {!audit && (
              <button className="btn primary" onClick={runAudit} disabled={busy}>
                {busy ? "审计中..." : "执行行动前审计"}
              </button>
            )}
            {(needsConfirm || (effectiveBlocked && !versionBlocked)) && (
              <button className="btn primary" onClick={runAudit} disabled={busy}>
                {busy ? "审计中..." : "重新审计"}
              </button>
            )}
            {versionBlocked && (
              <button className="btn success" onClick={fixTask} disabled={busy}>
                ✓ 一键修正为当前版本
              </button>
            )}
            {canStart && (
              <button className="btn success" onClick={startTask} disabled={busy}>
                ▶ 启动任务
              </button>
            )}
            {task?.status === "running" && (
              <div className="flex items-center gap-2">
                <span className="tag green">任务进行中</span>
                <button className="btn ghost" onClick={() => navigate(`/result/${task.task_id}`)}>
                  去提交结果 →
                </button>
              </div>
            )}
            {task?.status === "completed" && (
              <div className="flex items-center gap-2">
                <span className="tag green">任务已完成</span>
                <button className="btn ghost" onClick={() => navigate(`/result/${task.task_id}`)}>
                  去提交结果 →
                </button>
              </div>
            )}
            {task?.status === "blocked" && <span className="tag red">任务已阻断</span>}
          </div>
        </div>

        <div className="card">
          <div className="section-title">
            <b>变更影响分析</b>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="p-3 rounded-xl" style={{ background: "var(--red-soft)" }}>
              <div className="text-2xl font-bold text-red-600">
                {compare.affected_objects.tasks || 0}
              </div>
              <div className="text-xs muted mt-0.5">受影响任务</div>
            </div>
            <div className="p-3 rounded-xl" style={{ background: "var(--amber-soft)" }}>
              <div className="text-2xl font-bold text-amber-700">
                {compare.affected_objects.meetings || 0}
              </div>
              <div className="text-xs muted mt-0.5">相关会议</div>
            </div>
            <div className="p-3 rounded-xl" style={{ background: "var(--blue-soft)" }}>
              <div className="text-2xl font-bold text-blue-600">
                {compare.affected_objects.results || 0}
              </div>
              <div className="text-xs muted mt-0.5">历史结果</div>
            </div>
          </div>
          <p className="text-xs muted mt-3">
            历史记录永久保留，旧版本不被删除或静默覆盖。
          </p>
        </div>
      </div>

      {/* 审计事件 */}
      <div className="card">
        <div className="section-title">
          <b>审计事件</b>
        </div>
        <div className="audit-trail">
          <div className="entry">
            任务 <span className="font-mono">{compare.task_id.slice(0, 16)}...</span> 创建
            <br />
            <span className="text-muted">
              绑定主张 {compare.old_claim?.claim_id || "-"}
            </span>
          </div>
          {versionBlocked && (
            <div className="entry danger">
              版本规则触发：旧主张已被 {compare.current_claim?.claim_id} 替代
              <br />
              <span className="text-muted">自动阻断，待人工确认</span>
            </div>
          )}
          {audit && (
            <div className={`entry ${audit.status === "passed" ? "success" : audit.status === "needs_confirmation" ? "warn" : "danger"}`}>
              审计执行完成：
              <b className={audit.status === "passed" ? "text-green-600" : audit.status === "needs_confirmation" ? "text-amber-600" : "text-red-600"}>
                {audit.status === "passed" ? "通过" : audit.status === "needs_confirmation" ? "需确认" : audit.status}
              </b>
              {audit.status !== "passed" && audit.result && (
                <>
                  <br />
                  <span className="text-muted">
                    {[...(audit.result.reasons || []), ...(audit.result.confirmations || [])].join("；")}
                  </span>
                </>
              )}
            </div>
          )}
          {task?.status === "running" && (
            <div className="entry success">任务已启动并运行中</div>
          )}
          {task?.status === "completed" && (
            <div className="entry success">任务已完成，等待结果回流</div>
          )}
          {task?.status === "blocked" && (
            <div className="entry danger">任务保持 blocked 状态</div>
          )}
        </div>
      </div>

      {/* 资源补充弹窗 */}
      {resourceModalOpen && (
        <ResourceModal
          onClose={() => setResourceModalOpen(false)}
          onSubmit={saveResources}
        />
      )}
    </div>
  );
}

function ApprovalTag({ status }: { status?: string }) {
  if (status === "approved") return <span className="tag green">已审批</span>;
  if (status === "rejected") return <span className="tag red">已拒绝</span>;
  return <span className="tag amber">待审批</span>;
}

function ResourceSummary({ resources }: { resources?: Record<string, unknown> | null }) {
  const materials = (resources?.materials as { name?: string; amount?: string }[]) || [];
  const equipment = (resources?.equipment as { name?: string; status?: string }[]) || [];
  const scheduled = (resources?.scheduled_at as string | null) || null;
  const note = (resources?.note as string | null) || null;
  return (
    <div className="text-xs text-slate-600 space-y-1.5">
      {materials.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {materials.map((m, i) => (
            <span key={i} className="tag blue" style={{ padding: "2px 9px", fontWeight: 500 }}>
              {m.name}{m.amount ? ` ${m.amount}` : ""}
            </span>
          ))}
        </div>
      )}
      {equipment.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {equipment.map((e, i) => (
            <span key={i} className="tag purple" style={{ padding: "2px 9px", fontWeight: 500 }}>
              {e.name}{e.status ? ` · ${e.status}` : ""}
            </span>
          ))}
        </div>
      )}
      {scheduled && <div>排期：{new Date(scheduled).toLocaleString()}</div>}
      {note && <div>备注：{note}</div>}
    </div>
  );
}

function CheckCard({
  label,
  status,
  detail,
}: {
  label: string;
  status: CheckStatus;
  detail: string;
}) {
  const map: Record<CheckStatus, { text: string; color: string; bg: string }> = {
    passed: { text: "通过", color: "var(--green)", bg: "var(--green-soft)" },
    needs_confirmation: { text: "需确认", color: "#8a5e00", bg: "var(--amber-soft)" },
    blocked: { text: "阻断", color: "var(--red)", bg: "var(--red-soft)" },
    pending: { text: "待审计", color: "var(--muted)", bg: "#eef2f7" },
  };
  const m = map[status];
  return (
    <div className="card p-4" style={{ background: m.bg }}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs muted font-semibold">{label}</span>
        <span className="badge-dot" style={{ background: m.color }} />
      </div>
      <b className="block text-lg" style={{ color: m.color }}>
        {m.text}
      </b>
      <span className="text-xs muted mt-1 block" style={{ lineHeight: 1.5 }}>
        {detail}
      </span>
    </div>
  );
}

function VersionCard({
  variant,
  tagLabel,
  claim,
}: {
  variant: "old" | "current";
  tagLabel: string;
  claim: {
    claim_id: string;
    parameter_version?: {
      parameters?: { name: string; value: string; unit?: string }[];
      version?: string;
      scope?: Record<string, unknown>;
    } | null;
    content?: Record<string, unknown>;
  };
}) {
  const params = claim.parameter_version?.parameters || [];
  const isCurrent = variant === "current";
  return (
    <div
      className="rounded-2xl p-5 flex flex-col"
      style={{
        background: isCurrent ? "#f5fff9" : "#fffafb",
        border: `1px solid ${isCurrent ? "#b4dcc8" : "#f0c6c9"}`,
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <span className={`tag ${isCurrent ? "green" : "red"}`}>{tagLabel}</span>
        <span className="text-xs font-mono muted">
          v{claim.parameter_version?.version || "?"}
        </span>
      </div>

      <div className="flex-1">
        {params.length > 0 && (
          <div className="space-y-2 mb-3">
            {params.map((p, i) => (
              <div key={i} className="flex items-baseline gap-1">
                <span className="text-xs text-slate-500 mr-1">{p.name}</span>
                <span className="text-3xl font-bold" style={{ color: isCurrent ? "var(--green)" : "var(--red)" }}>
                  {p.value}
                </span>
                <span className="text-sm text-muted">{p.unit}</span>
              </div>
            ))}
          </div>
        )}
        {claim.parameter_version?.scope && (
          <div
            className="rounded-xl p-2.5 text-xs"
            style={{ background: "rgba(255,255,255,0.7)" }}
          >
            <b className="text-slate-700">适用范围：</b>
            {Object.entries(claim.parameter_version.scope)
              .map(([k, v]) => `${k}=${String(v)}`)
              .join(" / ")}
          </div>
        )}
      </div>

      <div className="text-xs text-muted mt-3 pt-3 border-t border-white/60">
        主张 ID: <span className="font-mono">{claim.claim_id.slice(0, 14)}...</span>
      </div>
    </div>
  );
}

function ResourceModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (payload: Parameters<typeof apiUpdateResources>[1]) => Promise<void>;
}) {
  const [materialRows, setMaterialRows] = useState<ParamRow[]>([]);
  const [equipmentRows, setEquipmentRows] = useState<ParamRow[]>([]);
  const [scheduledAt, setScheduledAt] = useState("");
  const [note, setNote] = useState("");
  const [assignee, setAssignee] = useState("");

  const submit = async () => {
    const materials = materialRows
      .filter((r) => r.name.trim())
      .map((r) => ({ name: r.name.trim(), amount: r.value.trim() || undefined }));
    const equipment = equipmentRows
      .filter((r) => r.name.trim())
      .map((r) => ({ name: r.name.trim(), status: r.value.trim() || undefined }));
    await onSubmit({
      materials,
      equipment,
      scheduled_at: scheduledAt || undefined,
      assignee_username: assignee.trim() || undefined,
      note: note.trim() || undefined,
    });
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="section-title">
          <b>补充资源信息</b>
          <span className="section-meta">提交后资源门标记为已就绪</span>
        </div>
        <div className="space-y-4">
          <div className="field">
            <label className="field-label">物料（名称 + 用量）</label>
            <ParameterEditor
              rows={materialRows}
              onChange={setMaterialRows}
              mode="kv"
              namePlaceholder="物料名"
              valuePlaceholder="用量，如 500g"
              emptyHint="暂无物料，点击「+ 添加」录入"
            />
          </div>
          <div className="field">
            <label className="field-label">设备（名称 + 状态）</label>
            <ParameterEditor
              rows={equipmentRows}
              onChange={setEquipmentRows}
              mode="kv"
              namePlaceholder="设备名"
              valuePlaceholder="状态，如 可用"
              emptyHint="暂无设备，点击「+ 添加」录入"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="field">
              <label className="field-label">排期时间</label>
              <input
                type="datetime-local"
                className="input"
                value={scheduledAt}
                onChange={(e) => setScheduledAt(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="field-label">负责人用户名</label>
              <input
                className="input mono"
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
                placeholder="如 executor"
              />
            </div>
          </div>
          <div className="field">
            <label className="field-label">备注</label>
            <input
              className="input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="物料设备到位情况说明"
            />
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn" onClick={onClose}>
            取消
          </button>
          <button className="btn primary" onClick={submit}>
            提交资源信息
          </button>
        </div>
      </div>
    </div>
  );
}
