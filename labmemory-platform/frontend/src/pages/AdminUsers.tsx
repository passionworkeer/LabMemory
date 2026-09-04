import { Fragment, useCallback, useEffect, useState } from "react";
import {
  apiAddUserMember,
  apiListExperiments,
  apiListUsers,
  apiPatchUserRole,
  apiRemoveUserMember,
} from "../api";
import { dialog } from "../dialog";
import type { UserAdminOut, UserRole } from "../types";

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "viewer", label: "只读访客" },
  { value: "executor", label: "执行人" },
  { value: "lead", label: "实验负责人" },
  { value: "pi", label: "项目负责人" },
  { value: "admin", label: "管理员" },
];

const SOURCE_LABEL: Record<string, string> = {
  seed: "演示账号",
  feishu_auto: "飞书自动注册",
  manual: "手动创建",
};

const MEMBER_ROLES: { value: UserRole; label: string }[] = [
  { value: "viewer", label: "只读" },
  { value: "executor", label: "执行人" },
  { value: "lead", label: "实验负责人" },
  { value: "pi", label: "项目负责人" },
];

export default function AdminUsers() {
  const [users, setUsers] = useState<UserAdminOut[]>([]);
  const [experiments, setExperiments] = useState<{ experiment_id: string; name: string }[]>([]);
  const [err, setErr] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [addForm, setAddForm] = useState<Record<number, { experiment_id: string; role: UserRole }>>({});

  const load = useCallback(async () => {
    setErr("");
    try {
      const [us, exps] = await Promise.all([apiListUsers(), apiListExperiments()]);
      setUsers(us);
      setExperiments(exps.map((e) => ({ experiment_id: e.experiment_id, name: e.name })));
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const replaceUser = (updated: UserAdminOut) => {
    setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
  };

  const changeRole = async (u: UserAdminOut, role: UserRole) => {
    try {
      replaceUser(await apiPatchUserRole(u.id, role));
    } catch (e) {
      await dialog.alert({ message: "修改角色失败：" + (e as Error).message, variant: "error" });
    }
  };

  const addMember = async (u: UserAdminOut) => {
    const f = addForm[u.id];
    if (!f?.experiment_id) return;
    try {
      replaceUser(await apiAddUserMember(u.id, f.experiment_id, f.role));
      setAddForm((prev) => ({ ...prev, [u.id]: { experiment_id: "", role: "viewer" } }));
    } catch (e) {
      await dialog.alert({ message: "添加可见实验失败：" + (e as Error).message, variant: "error" });
    }
  };

  const removeMember = async (u: UserAdminOut, experimentId: string) => {
    const ok = await dialog.confirm({
      title: "收回可见权限",
      message: `将移除 ${u.display_name} 对实验 ${experimentId} 的访问权限，确认？`,
      variant: "warning",
      danger: true,
    });
    if (!ok) return;
    try {
      replaceUser(await apiRemoveUserMember(u.id, experimentId));
    } catch (e) {
      await dialog.alert({ message: "移除失败：" + (e as Error).message, variant: "error" });
    }
  };

  return (
    <div className="fade-in">
      {err && (
        <div className="alert-inline error">
          <span className="ai-icon">⚠</span>
          <span>{err}</span>
        </div>
      )}

      <div
        className="card mb-5"
        style={{ background: "rgba(51,112,255,0.04)", border: "1px solid rgba(51,112,255,0.18)" }}
      >
        <div className="text-sm leading-relaxed">
          <b className="text-slate-700">飞书 UUAP 用户与可见范围</b>
          <p className="text-slate-500 mt-1">
            通过飞书登录的新用户将<b>自动注册</b>，默认最低权限「只读访客（viewer）」——未分配实验成员时不可见任何实验数据。
            管理员可在下方调整每位用户的<b>全局角色</b>，并通过<b>实验成员</b>精确控制其能看到的实验范围
            （实验级角色支持 只读 / 执行人 / 实验负责人 / 项目负责人）。
          </p>
        </div>
      </div>

      <div className="card">
        <div className="section-title">
          <b>用户列表</b>
          <span className="section-meta">{users.length} 个用户</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>用户</th>
              <th>来源</th>
              <th>全局角色</th>
              <th>可见实验</th>
              <th>飞书 ID</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isOpen = expanded === u.id;
              const f = addForm[u.id] || { experiment_id: "", role: "viewer" as UserRole };
              return (
                <Fragment key={u.id}>
                  <tr>
                    <td>
                      <div className="text-sm font-medium">{u.display_name}</div>
                      <div className="font-mono text-xs text-slate-400">{u.username}</div>
                    </td>
                    <td>
                      <span className={`tag ${u.source === "feishu_auto" ? "blue" : "gray"}`}>
                        {SOURCE_LABEL[u.source] || u.source}
                      </span>
                    </td>
                    <td>
                      <select
                        className="input"
                        style={{ width: 130 }}
                        value={u.global_role}
                        onChange={(e) => changeRole(u, e.target.value as UserRole)}
                      >
                        {ROLE_OPTIONS.map((r) => (
                          <option key={r.value} value={r.value}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="text-xs">
                      <span className="tag gray">{u.experiment_count}</span>
                      {u.experiment_count > 0 && (
                        <span className="ml-1 text-slate-400">
                          {u.members.map((m) => m.role).join(", ")}
                        </span>
                      )}
                    </td>
                    <td className="font-mono text-xs text-slate-400">{u.feishu_user_id || "-"}</td>
                    <td>
                      <button className="btn sm ghost" onClick={() => setExpanded(isOpen ? null : u.id)}>
                        {isOpen ? "收起" : "可见范围"}
                      </button>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={6} className="p-0">
                        <div className="p-4" style={{ background: "var(--line-light)" }}>
                          <div className="text-sm font-semibold mb-3 flex items-center gap-2">
                            <span className="badge-dot blue" />
                            可见实验范围（{u.display_name}）
                          </div>
                          {u.members.length === 0 && (
                            <div className="text-xs text-slate-400 mb-3">
                              尚未分配任何实验，登录后不可见任何实验数据。
                            </div>
                          )}
                          {u.members.length > 0 && (
                            <div className="flex flex-wrap gap-2 mb-3">
                              {u.members.map((m) => (
                                <span key={m.id} className="tag blue" style={{ padding: "4px 10px" }}>
                                  {m.experiment_id}
                                  <span className="opacity-60 ml-2">
                                    {MEMBER_ROLES.find((r) => r.value === m.role)?.label || m.role}
                                  </span>
                                  <button
                                    className="ml-2 text-red-500 hover:text-red-700"
                                    title="移除可见权限"
                                    onClick={() => m.experiment_id && removeMember(u, m.experiment_id)}
                                  >
                                    ✕
                                  </button>
                                </span>
                              ))}
                            </div>
                          )}
                          <div className="flex gap-3 items-end">
                            <div className="field mb-0" style={{ minWidth: 220 }}>
                              <label className="field-label">添加可见实验</label>
                              <select
                                className="input"
                                value={f.experiment_id}
                                onChange={(e) =>
                                  setAddForm({ ...addForm, [u.id]: { ...f, experiment_id: e.target.value } })
                                }
                              >
                                <option value="">选择实验</option>
                                {experiments.map((e) => (
                                  <option key={e.experiment_id} value={e.experiment_id}>
                                    {e.experiment_id} - {e.name}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <div className="field mb-0">
                              <label className="field-label">实验内角色</label>
                              <select
                                className="input"
                                value={f.role}
                                onChange={(e) =>
                                  setAddForm({ ...addForm, [u.id]: { ...f, role: e.target.value as UserRole } })
                                }
                              >
                                {MEMBER_ROLES.map((r) => (
                                  <option key={r.value} value={r.value}>
                                    {r.label}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <button
                              className="btn primary sm"
                              onClick={() => addMember(u)}
                              disabled={!f.experiment_id}
                            >
                              添加
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
