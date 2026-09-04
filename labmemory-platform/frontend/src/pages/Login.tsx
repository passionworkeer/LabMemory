import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { apiFeishuAuthorize, apiFeishuMockLogin, apiLogin } from "../api";
import type { FeishuAuthorizeOut, LoginOut, User } from "../types";
import { useAuth } from "../store";
import AnimatedBackground from "../components/AnimatedBackground";

function decodeUserB64(raw: string): User | null {
  try {
    const b64 = raw.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64.padEnd(b64.length + ((4 - (b64.length % 4)) % 4), "=");
    return JSON.parse(atob(padded));
  } catch {
    return null;
  }
}

export default function Login() {
  const { setAuth } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from || "/tower";

  // 密码登录（管理员/演示兜底）
  const [username, setUsername] = useState("pi");
  const [password, setPassword] = useState("123456");
  const [pwLoading, setPwLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);

  // 飞书 UUAP 登录
  const [feishu, setFeishu] = useState<FeishuAuthorizeOut | null>(null);
  const [mockKey, setMockKey] = useState("");
  const [mockName, setMockName] = useState("");
  const [mockLoading, setMockLoading] = useState(false);

  const [err, setErr] = useState("");

  const goHome = (r: LoginOut) => {
    setAuth(r.access_token, r.user);
    navigate(from, { replace: true });
  };

  // 处理飞书回调重定向（token/user 参数）并初始化登录方式
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const userRaw = params.get("user");
    const error = params.get("error");
    if (error) setErr(decodeURIComponent(error));
    if (token && userRaw) {
      const user = decodeUserB64(userRaw);
      if (user) {
        setAuth(token, user);
        window.history.replaceState({}, "", "/login");
        navigate(from, { replace: true });
        return;
      }
    }
    apiFeishuAuthorize()
      .then(setFeishu)
      .catch((e) => setErr((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handlePwSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwLoading(true);
    setErr("");
    try {
      goHome(await apiLogin(username, password));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setPwLoading(false);
    }
  };

  const handleFeishuLogin = () => {
    if (feishu?.authorize_url) window.location.href = feishu.authorize_url;
  };

  const handleMockSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMockLoading(true);
    setErr("");
    try {
      goHome(await apiFeishuMockLogin(mockKey, mockName || undefined));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setMockLoading(false);
    }
  };

  const isMock = feishu?.mode === "mock" && feishu.mock_enabled;
  const showFeishuBtn = !!feishu && !isMock && !!feishu.authorize_url;
  const pwEnabled = feishu ? feishu.password_login_enabled : true;

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <AnimatedBackground strong />

      <div className="relative z-10 w-full max-w-md">
        <div className="text-center mb-6">
          <div
            className="w-16 h-16 rounded-2xl font-extrabold text-white text-2xl grid place-items-center mx-auto mb-3"
            style={{
              background: "linear-gradient(135deg, #3370ff, #22b8cf)",
              animation: "glow-breathe 4s ease-in-out infinite, float-y 5s ease-in-out infinite",
            }}
          >
            LM
          </div>
          <h1 className="text-2xl font-bold gradient-text">LabMemory 晶研智流</h1>
          <p className="text-sm mt-1" style={{ color: "#5a7ba6" }}>可信实验决策与记忆平台</p>
        </div>

        <div
          className="rounded-2xl p-8"
          style={{
            background: "rgba(255,255,255,0.78)",
            border: "1px solid rgba(255,255,255,0.7)",
            boxShadow:
              "0 24px 64px rgba(26, 45, 85, 0.14), inset 0 1px 0 rgba(255,255,255,0.9)",
            backdropFilter: "blur(20px) saturate(160%)",
            WebkitBackdropFilter: "blur(20px) saturate(160%)",
          }}
        >
          <h2 className="text-lg font-bold mb-1">欢迎登录</h2>
          <p className="text-sm text-slate-500 mb-6">使用飞书账号一键进入工作空间</p>

          {!feishu && !err && (
            <div className="text-sm text-slate-400 mb-4">正在初始化登录方式…</div>
          )}

          {/* 飞书 UUAP 登录主入口 */}
          {showFeishuBtn && (
            <button
              type="button"
              onClick={handleFeishuLogin}
              className="w-full py-3 rounded-xl text-white font-semibold transition hover:opacity-90 active:scale-[0.99]"
              style={{
                background: "linear-gradient(135deg, #3370ff, #22b8cf)",
                boxShadow: "0 6px 18px rgba(51, 112, 255, 0.38)",
              }}
            >
              使用飞书登录
            </button>
          )}

          {/* mock 模式：模拟飞书免登 */}
          {isMock && (
            <form onSubmit={handleMockSubmit} className="space-y-4">
              <div className="field">
                <label className="field-label">模拟飞书用户（工号/姓名）</label>
                <input
                  type="text"
                  value={mockKey}
                  onChange={(e) => setMockKey(e.target.value)}
                  className="input lg"
                  placeholder="如 zhangsan（留空则随机新用户）"
                />
              </div>
              <div className="field">
                <label className="field-label">显示名（可选）</label>
                <input
                  type="text"
                  value={mockName}
                  onChange={(e) => setMockName(e.target.value)}
                  className="input lg"
                  placeholder="如 张三"
                />
              </div>
              <button
                type="submit"
                disabled={mockLoading}
                className="w-full py-3 rounded-xl text-white font-semibold transition hover:opacity-90 active:scale-[0.99]"
                style={{
                  background: "linear-gradient(135deg, #3370ff, #22b8cf)",
                  boxShadow: "0 6px 18px rgba(51, 112, 255, 0.38)",
                }}
              >
                {mockLoading ? "登录中..." : "模拟飞书登录"}
              </button>
            </form>
          )}

          {err && (
            <div
              className="text-sm py-2 px-3 rounded-lg text-red-600 mt-3"
              style={{ background: "var(--red-soft)" }}
            >
              {err}
            </div>
          )}

          {/* 密码登录（管理员/演示兜底） */}
          {pwEnabled && (
            <div className="mt-5 pt-4 border-t border-slate-100">
              {showPw ? (
                <form onSubmit={handlePwSubmit} className="space-y-4">
                  <div className="field">
                    <label className="field-label">用户名</label>
                    <input
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className="input lg"
                      placeholder="pi / lead / executor / admin"
                      autoFocus
                    />
                  </div>
                  <div className="field">
                    <label className="field-label">密码</label>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="input lg"
                      placeholder="123456"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={pwLoading}
                    className="w-full py-3 rounded-xl text-white font-semibold transition hover:opacity-90 active:scale-[0.99]"
                    style={{
                      background: "linear-gradient(135deg, #64748b, #94a3b8)",
                      boxShadow: "0 6px 18px rgba(100, 116, 139, 0.35)",
                    }}
                  >
                    {pwLoading ? "登录中..." : "登 录"}
                  </button>
                  <div className="flex gap-2 flex-wrap">
                    {["pi", "lead", "executor", "admin"].map((role) => (
                      <button
                        key={role}
                        type="button"
                        onClick={() => {
                          setUsername(role);
                          setPassword("123456");
                        }}
                        className="text-xs px-3 py-1.5 rounded-full border border-slate-200 hover:bg-slate-50 transition"
                      >
                        {role === "pi" ? "项目负责人" : role === "lead" ? "实验负责人" : role === "admin" ? "管理员" : "执行人"}
                      </button>
                    ))}
                  </div>
                </form>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowPw(true)}
                  className="text-xs text-slate-400 hover:text-slate-600 transition"
                >
                  管理员 / 演示账号密码登录 →
                </button>
              )}
            </div>
          )}
        </div>

        <p className="text-center text-xs mt-5" style={{ color: "#7d94b5" }}>
          © 2026 LabMemory · 晶研智流 · 溯研 LabTrace
        </p>
      </div>
    </div>
  );
}
