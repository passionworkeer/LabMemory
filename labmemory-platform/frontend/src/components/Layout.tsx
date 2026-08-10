import { useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../store";

const ROLE_LABEL: Record<string, string> = {
  pi: "项目负责人",
  lead: "实验负责人",
  executor: "执行人",
  admin: "管理员",
};

// 图标用内联 SVG，零依赖
const IconTower = () => (
  <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M3 13h8V3H3v10zM13 21h8V11h-8v10zM3 21h8v-6H3v6zM13 3h8v6h-8V3z" />
  </svg>
);
const IconReview = () => (
  <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M9 11l3 3L22 4" />
    <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
  </svg>
);
const IconAudit = () => (
  <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);
const IconResult = () => (
  <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
    <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
  </svg>
);
const IconExperiment = () => (
  <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M9 3v6l-6 13h18L15 9V3" />
    <path d="M9 3h6M6 16h12" />
  </svg>
);
const IconQA = () => (
  <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
    <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
    <circle cx="12" cy="17" r="0.5" fill="currentColor" />
  </svg>
);
const IconPassport = () => (
  <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <circle cx="12" cy="11" r="3" />
    <path d="M7 18c1-2 3-3 5-3s4 1 5 3" />
  </svg>
);

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType;
  piOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/tower", label: "研发控制塔", icon: IconTower },
  { to: "/review", label: "会后复核", icon: IconReview },
  { to: "/audit", label: "行动审计", icon: IconAudit },
  { to: "/result", label: "结果回流", icon: IconResult },
  { to: "/experiments", label: "实验管理", icon: IconExperiment, piOnly: true },
  { to: "/qa", label: "可信问答", icon: IconQA },
];

// 辅助：实验护照单独入口（放在底部，不作为主导航）
const EXTRA_ITEMS: NavItem[] = [
  { to: "/passport", label: "实验护照", icon: IconPassport },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [roleMenuOpen, setRoleMenuOpen] = useState(false);

  if (!user) return null;

  const isPI = user.global_role === "pi" || user.global_role === "admin";
  const navItems = NAV_ITEMS.filter((n) => !n.piOnly || isPI);

  return (
    <div className="grid h-screen" style={{ gridTemplateColumns: "240px minmax(0,1fr)" }}>
      <aside
        className="flex flex-col text-white sticky top-0 h-screen"
        style={{ background: "linear-gradient(180deg, #0e1e3c 0%, #142850 100%)", padding: "20px 14px" }}
      >
        {/* Logo */}
        <div className="flex gap-3 items-center px-2 pb-5 border-b border-white/10">
          <div
            className="rounded-xl font-extrabold grid place-items-center"
            style={{
              width: 42,
              height: 42,
              background: "linear-gradient(135deg,#4b80ff,#7c5cff)",
              boxShadow: "0 4px 14px rgba(124, 92, 255, 0.4)",
            }}
          >
            LM
          </div>
          <div>
            <b className="block text-base">LabMemory</b>
            <small className="text-slate-400 text-xs">晶研智流 · 可信决策</small>
          </div>
        </div>

        {/* 主导航 */}
        <nav className="flex flex-col gap-1 py-4 flex-1">
          <div className="text-xs text-slate-400 px-3 pb-2 uppercase tracking-wider font-medium">
            主功能
          </div>
          {navItems.map((n) => {
            const Icon = n.icon;
            return (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `sidebar-link ${isActive ? "active" : ""}`
                }
                end={n.to.split("/").length <= 2}
              >
                {({ isActive }) => (
                  <>
                    <Icon />
                    <span className="flex-1">{n.label}</span>
                    {isActive && (
                      <span
                        className="w-1.5 h-1.5 rounded-full"
                        style={{ background: "#7aa7ff", boxShadow: "0 0 6px #7aa7ff" }}
                      />
                    )}
                  </>
                )}
              </NavLink>
            );
          })}

          <div className="text-xs text-slate-400 px-3 pb-2 mt-4 uppercase tracking-wider font-medium">
            查看
          </div>
          {EXTRA_ITEMS.map((n) => {
            const Icon = n.icon;
            return (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `sidebar-link ${isActive ? "active" : ""}`
                }
              >
                {() => (
                  <>
                    <Icon />
                    <span className="flex-1">{n.label}</span>
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* 底部用户卡 */}
        <div
          className="border border-white/10 rounded-xl p-3 relative"
          style={{ background: "rgba(255,255,255,.05)" }}
        >
          <div
            className="flex items-center gap-2.5 cursor-pointer"
            onClick={() => setRoleMenuOpen(!roleMenuOpen)}
          >
            <div
              className="w-9 h-9 rounded-lg grid place-items-center font-bold text-sm"
              style={{
                background: "linear-gradient(135deg, #4b80ff, #7c5cff)",
              }}
            >
              {user.display_name.charAt(0)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold truncate">{user.display_name}</div>
              <div className="text-xs text-slate-400 truncate">
                {ROLE_LABEL[user.global_role] || user.global_role}
              </div>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </div>

          {roleMenuOpen && (
            <div
              className="absolute left-3 right-3 bottom-full mb-2 rounded-xl overflow-hidden shadow-xl"
              style={{ background: "rgba(20,40,80,0.98)", border: "1px solid rgba(255,255,255,0.1)" }}
            >
              <div className="py-1">
                <div className="px-3 py-1.5 text-xs text-slate-400 border-b border-white/10">
                  当前角色
                </div>
                {["pi", "lead", "executor"].map((role) => (
                  <div
                    key={role}
                    className={`px-3 py-2 text-sm cursor-pointer flex items-center gap-2 ${
                      user.global_role === role ? "text-white bg-white/10" : "text-slate-300 hover:bg-white/5"
                    }`}
                  >
                    {user.global_role === role && (
                      <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                    )}
                    {ROLE_LABEL[role]}
                  </div>
                ))}
                <div className="border-t border-white/10 mt-1 pt-1">
                  <button
                    className="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-white/5"
                    onClick={() => {
                      logout();
                      navigate("/login");
                    }}
                  >
                    退出登录
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

      </aside>

      <main className="min-w-0 flex flex-col h-screen overflow-hidden">
        {location.pathname !== "/tower" && (
          <header
            className="flex-shrink-0 flex items-center px-6 gap-3"
            style={{
              height: 64,
              background: "rgba(255,255,255,.85)",
              backdropFilter: "blur(12px)",
              borderBottom: "1px solid var(--line)",
            }}
          >
            <PageHeader />
          </header>
        )}
        <div className="flex-1 overflow-auto p-6 fade-in">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

const LABEL_MAP: Record<string, string> = {
  tower: "研发控制塔",
  review: "会后复核",
  audit: "行动审计",
  result: "结果回流",
  experiments: "实验管理",
  qa: "可信问答",
  passport: "实验护照",
  brief: "会前研讨包",
  compiler: "决策编译器",
};

const PARENT_LABEL: Record<string, string> = {
  review: "复核列表",
  audit: "审计列表",
  result: "结果列表",
  passport: "实验护照",
  brief: "实验管理",
  compiler: "会后复核",
};

function PageHeader() {
  const location = useLocation();
  const { title, subLabel, parentPath, parentLabel } = useMemo(() => {
    const parts = location.pathname.split("/").filter(Boolean);
    const first = parts[0] || "tower";
    const isSub = parts.length > 1;
    return {
      title: LABEL_MAP[first] || first,
      subLabel: isSub ? parts[1].slice(0, 16) : "",
      parentPath: isSub ? `/${first}` : "",
      parentLabel: PARENT_LABEL[first] || "返回",
    };
  }, [location.pathname]);

  return (
    <>
      {parentPath && (
        <NavLink to={parentPath} className="back-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
          <span>{parentLabel}</span>
        </NavLink>
      )}
      {parentPath && <span className="text-slate-300">/</span>}
      <div className="flex items-baseline gap-2 min-w-0">
        <span className="text-lg font-bold text-slate-800 truncate">{title}</span>
        {subLabel && (
          <span className="text-xs text-slate-400 font-mono truncate">{subLabel}</span>
        )}
      </div>
    </>
  );
}
