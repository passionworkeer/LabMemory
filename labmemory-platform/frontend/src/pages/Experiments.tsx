import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiAddMember, apiCreateExperiment, apiListExperiments, apiListProjects } from "../api";
import { dialog } from "../dialog";
import type { ExperimentOut, ProjectOut } from "../types";

export default function Experiments() {
  const [experiments, setExperiments] = useState<ExperimentOut[]>([]);
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [err, setErr] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newExp, setNewExp] = useState({
    experiment_id: "",
    project_id: "",
    name: "",
    owner_username: "lead",
  });
  const [memberAdd, setMemberAdd] = useState<{ expId: string; username: string; role: "pi" | "lead" | "executor" }>({
    expId: "",
    username: "",
    role: "executor",
  });

  const load = () => {
    Promise.all([apiListExperiments(), apiListProjects()])
      .then(([es, ps]) => {
        setExperiments(es);
        setProjects(ps);
      })
      .catch((e) => setErr(e.message));
  };
  useEffect(load, []);

  const create = async () => {
    try {
      await apiCreateExperiment(newExp);
      setNewExp({ experiment_id: "", project_id: "", name: "", owner_username: "lead" });
      setShowCreate(false);
      load();
    } catch (e) {
      await dialog.alert({ message: "创建失败：" + (e as Error).message, variant: "error" });
    }
  };

  const addMember = async () => {
    if (!memberAdd.expId || !memberAdd.username) return;
    try {
      await apiAddMember(memberAdd.expId, memberAdd.username, memberAdd.role);
      setMemberAdd({ expId: "", username: "", role: "executor" });
      load();
    } catch (e) {
      await dialog.alert({ message: "添加失败：" + (e as Error).message, variant: "error" });
    }
  };

  return (
    <div className="fade-in">
      <div className="flex justify-between items-center mb-4">
        <span className="text-sm muted">管理实验项目、成员与权限。仅 PI 可操作。</span>
        <button className="btn primary" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "取消" : "+ 创建实验"}
        </button>
      </div>

      {err && <div className="text-red-500 text-sm mb-3">{err}</div>}

      {showCreate && (
        <div className="card mb-5">
          <div className="section-title">
            <b>新建实验</b>
            <span className="section-meta">填写实验身份与负责人</span>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="field">
              <label className="field-label">实验编号 <span className="req">*</span></label>
              <input
                className="input mono"
                value={newExp.experiment_id}
                onChange={(e) => setNewExp({ ...newExp, experiment_id: e.target.value })}
                placeholder="EXP-XXX-001"
              />
              <span className="field-hint">建议格式：EXP-{`<团队>`}-{`<序号>`}</span>
            </div>
            <div className="field">
              <label className="field-label">所属项目</label>
              <select
                className="input"
                value={newExp.project_id}
                onChange={(e) => setNewExp({ ...newExp, project_id: e.target.value })}
              >
                <option value="">选择项目</option>
                {projects.map((p) => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.project_id} - {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label">实验名称</label>
              <input
                className="input"
                value={newExp.name}
                onChange={(e) => setNewExp({ ...newExp, name: e.target.value })}
                placeholder="如：催化剂用量优化 - 第 3 轮"
              />
            </div>
            <div className="field">
              <label className="field-label">负责人用户名</label>
              <input
                className="input mono"
                value={newExp.owner_username}
                onChange={(e) => setNewExp({ ...newExp, owner_username: e.target.value })}
                placeholder="lead"
              />
            </div>
          </div>
          <div className="mt-4 flex justify-end">
            <button className="btn success" onClick={create}>
              创建实验
            </button>
          </div>
        </div>
      )}

      <div className="card mb-5">
        <div className="section-title">
          <b>实验列表</b>
          <span className="section-meta">{experiments.length} 个实验</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>实验名称</th>
              <th>experiment_id</th>
              <th>所属项目</th>
              <th>状态</th>
              <th>成员</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {experiments.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <div className="empty-state">
                    <div className="empty-icon">🧪</div>
                    <div className="empty-title">暂无实验</div>
                    <div className="empty-desc">点击右上角"创建实验"开始第一个项目。</div>
                  </div>
                </td>
              </tr>
            )}
            {experiments.map((e) => (
              <tr key={e.experiment_id}>
                <td className="text-sm font-medium">{e.name}</td>
                <td className="font-mono text-xs text-slate-500">{e.experiment_id}</td>
                <td className="text-xs">{e.project_id}</td>
                <td>
                  <span className="tag gray">{e.status}</span>
                </td>
                <td className="text-xs">
                  <div className="flex flex-wrap gap-1">
                    {e.members.map((m) => (
                      <span key={m.id} className="tag blue" style={{ padding: "2px 8px" }}>
                        {m.display_name}
                        <span className="opacity-60 ml-1">{m.role}</span>
                      </span>
                    ))}
                  </div>
                </td>
                <td>
                  <div className="flex gap-2">
                    <Link to={`/passport/${e.experiment_id}`} className="btn sm ghost">
                      护照
                    </Link>
                    <Link to={`/brief/${e.experiment_id}`} className="btn sm ghost">
                      简报
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="section-title">
          <b>添加成员</b>
          <span className="section-meta">为已有实验追加 PI / Lead / Executor</span>
        </div>
        <div className="grid grid-cols-4 gap-3">
          <div className="field">
            <label className="field-label">选择实验</label>
            <select
              className="input"
              value={memberAdd.expId}
              onChange={(e) => setMemberAdd({ ...memberAdd, expId: e.target.value })}
            >
              <option value="">选择实验</option>
              {experiments.map((e) => (
                <option key={e.experiment_id} value={e.experiment_id}>
                  {e.experiment_id}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field-label">用户名</label>
            <input
              className="input mono"
              placeholder="如 executor"
              value={memberAdd.username}
              onChange={(e) => setMemberAdd({ ...memberAdd, username: e.target.value })}
            />
          </div>
          <div className="field">
            <label className="field-label">角色</label>
            <select
              className="input"
              value={memberAdd.role}
              onChange={(e) => setMemberAdd({ ...memberAdd, role: e.target.value as "pi" | "lead" | "executor" })}
            >
              <option value="pi">PI</option>
              <option value="lead">Lead</option>
              <option value="executor">Executor</option>
            </select>
          </div>
          <div className="flex items-end">
            <button className="btn primary w-full" onClick={addMember}>
              添加成员
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
