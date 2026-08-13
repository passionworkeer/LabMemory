import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { apiLogin } from "../api";
import { useAuth } from "../store";
import AnimatedBackground from "../components/AnimatedBackground";

export default function Login() {
  const [username, setUsername] = useState("pi");
  const [password, setPassword] = useState("123456");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const { setAuth } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErr("");
    try {
      const r = await apiLogin(username, password);
      setAuth(r.access_token, r.user);
      const from = (loc.state as { from?: string } | null)?.from || "/tower";
      navigate(from, { replace: true });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

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
          <p className="text-sm text-slate-500 mb-6">使用你的账号进入工作空间</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="field">
              <label className="field-label">用户名</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input lg"
                placeholder="pi / lead / executor"
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

            {err && (
              <div
                className="text-sm py-2 px-3 rounded-lg text-red-600"
                style={{ background: "var(--red-soft)" }}
              >
                {err}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl text-white font-semibold transition hover:opacity-90 active:scale-[0.99]"
              style={{
                background: "linear-gradient(135deg, #3370ff, #22b8cf)",
                boxShadow: "0 6px 18px rgba(51, 112, 255, 0.38)",
              }}
            >
              {loading ? "登录中..." : "登 录"}
            </button>
          </form>

          <div className="mt-5 pt-4 border-t border-slate-100">
            <p className="text-xs text-slate-400 mb-2">演示账号（密码均为 123456）</p>
            <div className="flex gap-2 flex-wrap">
              {["pi", "lead", "executor"].map((role) => (
                <button
                  key={role}
                  type="button"
                  onClick={() => {
                    setUsername(role);
                    setPassword("123456");
                  }}
                  className="text-xs px-3 py-1.5 rounded-full border border-slate-200 hover:bg-slate-50 transition"
                >
                  {role === "pi" ? "项目负责人" : role === "lead" ? "实验负责人" : "执行人"}
                </button>
              ))}
            </div>
          </div>
        </div>

        <p className="text-center text-xs mt-5" style={{ color: "#7d94b5" }}>
          © 2026 LabMemory · 晶研智流 · 溯研 LabTrace
        </p>
      </div>
    </div>
  );
}
