import { useEffect, useState } from "react";
import { Loading, ErrorState } from "../components/State";
import { useNavigate } from "react-router-dom";
import { apiControlTower, apiResetDemo } from "../api";
import { dialog } from "../dialog";
import type { ControlTowerOut } from "../types";

export default function ControlTower() {
  const [data, setData] = useState<ControlTowerOut | null>(null);
  const [err, setErr] = useState("");
  const [resetBusy, setResetBusy] = useState(false);
  const navigate = useNavigate();

  const handleReset = async (mode: "clear" | "pending" | "full") => {
    const labels = { clear: "清空", pending: "待复核", full: "完整链路" };
    const ok = await dialog.confirm({
      title: "重置演示数据",
      message: `确认将演示数据重置为「${labels[mode]}」模式？\n当前所有业务数据将被清除。`,
      danger: true,
      confirmText: "确认重置",
    });
    if (!ok) return;
    setResetBusy(true);
    try {
      const r = await apiResetDemo(mode);
      await dialog.alert({ message: r.message, variant: "success" });
      load();
    } catch (e) {
      await dialog.alert({ message: "重置失败：" + (e as Error).message, variant: "error" });
    } finally {
      setResetBusy(false);
    }
  };

  const load = () => {
    apiControlTower().then(setData).catch((e) => setErr(e.message));
  };
  useEffect(load, []);

  if (err) return <ErrorState message={err} />;
  if (!data) return <Loading />;

  const kpis = [
    { label: "待复核候选", value: data.pending_reviews, sub: "会议决策待确认", icon: "📋", color: "var(--blue)", bg: "var(--blue-soft)" },
    { label: "行动前阻断", value: data.blocked_tasks, sub: "旧参数 / 未审批", icon: "🛡", color: "var(--red)", bg: "var(--red-soft)" },
    { label: "接口 / 证据异常", value: data.anomalies, sub: "可重试补偿", icon: "⚠", color: "var(--amber)", bg: "var(--amber-soft)" },
    { label: "24h 知识发布", value: data.published_24h, sub: "模拟试点口径", icon: "📖", color: "var(--green)", bg: "var(--green-soft)" },
    { label: "活跃实验", value: data.active_experiments, sub: "进行中项目", icon: "🧪", color: "var(--purple)", bg: "var(--purple-soft)" },
  ];

  return (
    <div className="fade-in">
      {/* Hero */}
      <div
        className="rounded-2xl p-7 text-white relative overflow-hidden mb-6"
        style={{
          background: "linear-gradient(135deg,#0a1a38 0%,#10457f 55%,#178fa6 100%)",
          boxShadow: "0 12px 32px rgba(16,69,127,0.28)",
        }}
      >
        <div
          className="absolute"
          style={{
            width: 320,
            height: 320,
            borderRadius: "50%",
            right: -80,
            top: -140,
            background: "rgba(255,255,255,0.06)",
          }}
        />
        <div
          className="absolute"
          style={{
            width: 200,
            height: 200,
            borderRadius: "50%",
            right: 100,
            bottom: -100,
            background: "rgba(34, 184, 207, 0.2)",
          }}
        />
        <div className="relative">
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
            style={{ background: "rgba(255,255,255,0.15)", color: "#fff" }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            实验室运行中
          </span>
          <h1 className="text-2xl font-bold mt-3 mb-2 leading-tight">
            让每条参数有证据，让每次执行用对版本
          </h1>
          <p className="text-sm max-w-3xl leading-relaxed" style={{ color: "#d6e2ff" }}>
            飞书会议负责承接协同，ELN/LIMS/机器人平台保留权威实验事实。LabMemory 将自然语言讨论编译为可审核的决策对象，
            用实验护照贯通参数、任务、结果和异常，并在执行前阻断旧参数或未解决冲突。
          </p>
          <div className="flex gap-2 flex-wrap mt-4">
            {["会前带版本资料包", "会中决策编译", "会后证据复核", "按生效版本执行", "结果反向校正知识", "失败边界与模型反馈"].map((s) => (
              <span
                key={s}
                className="text-xs px-3 py-1.5 rounded-full"
                style={{ border: "1px solid rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.08)" }}
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-5 gap-4 mb-6 max-md:grid-cols-2">
        {kpis.map((k) => (
          <div
            key={k.label}
            className="card metric-card"
            style={{ position: "relative", overflow: "hidden" }}
          >
            <div
              className="absolute right-4 top-4 w-10 h-10 rounded-xl grid place-items-center text-lg"
              style={{ background: k.bg }}
            >
              {k.icon}
            </div>
            <small className="text-muted">{k.label}</small>
            <strong style={{ color: k.color }}>{k.value}</strong>
            <em className="text-xs" style={{ color: "var(--muted)" }}>
              {k.sub}
            </em>
          </div>
        ))}
      </div>

      {/* 需要处理 */}
      <div className="card mb-6">
        <div className="section-title">
          <b>需要你处理</b>
          <span className="section-meta">{data.need_attention.length} 项</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>实验</th>
              <th>事项</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {data.need_attention.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <div className="empty-state">
                    <div className="empty-icon">🎉</div>
                    <div className="empty-title">暂无待处理项</div>
                    <div className="empty-desc">所有任务都在轨道上。</div>
                  </div>
                </td>
              </tr>
            )}
            {data.need_attention.map((n) => (
              <tr key={n.target_id} className="hover:bg-slate-50/50 transition">
                <td>
                  <div className="font-semibold text-sm">{n.experiment_id}</div>
                  <div className="text-xs muted font-mono">{n.target_id}</div>
                </td>
                <td className="text-sm">{n.title}</td>
                <td>
                  <span className={`tag ${n.severity === "high" ? "red" : "amber"}`}>
                    {n.status}
                  </span>
                </td>
                <td>
                  <button
                    className="btn sm ghost"
                    onClick={() => {
                      if (n.type === "pending_review") navigate(`/review/${n.target_id}`);
                      else if (n.type === "blocked_task") navigate(`/audit/${n.target_id}`);
                    }}
                  >
                    处理
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 演示提示 + 重置 */}
      <div
        className="rounded-xl p-4 text-sm flex items-start justify-between gap-4 flex-wrap"
        style={{
          background: "var(--cyan-soft)",
          border: "1px solid #b9e8ef",
          color: "#0b8a9e",
        }}
      >
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <span className="text-lg leading-none flex-shrink-0">💡</span>
          <div className="min-w-0">
            <b>快速开始 Demo</b>
            <p className="mt-1 text-xs leading-relaxed" style={{ color: "#33a0b2" }}>
              从"会后复核"开始 → 选择待确认会议 → 修改后确认 → 行动审计 → 结果回流 → 实验护照，完整跑通端到端闭环。
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap flex-shrink-0">
          <button
            className="btn sm"
            style={{ background: "rgba(255,255,255,0.75)", borderColor: "#9fdde8", color: "#0b8a9e" }}
            onClick={() => handleReset("pending")}
            disabled={resetBusy}
          >
            {resetBusy ? "重置中..." : "重置为待复核"}
          </button>
          <button
            className="btn sm"
            style={{ background: "rgba(255,255,255,0.75)", borderColor: "#9fdde8", color: "#0b8a9e" }}
            onClick={() => handleReset("full")}
            disabled={resetBusy}
          >
            重置为完整链路
          </button>
          <button
            className="btn sm ghost"
            style={{ background: "rgba(255,255,255,0.5)", borderColor: "#9fdde8", color: "#0b8a9e" }}
            onClick={() => handleReset("clear")}
            disabled={resetBusy}
          >
            清空
          </button>
        </div>
      </div>
    </div>
  );
}
