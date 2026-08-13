import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * 全局渲染异常兜底：任一子树渲染抛错时降级为友好错误页，
 * 避免整屏白屏（React 渲染期错误无法被 try/catch 捕获，只能靠边界）。
 * 样式全部内联，保证即便 CSS 未加载/加载出错也能正常展示兜底 UI。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 控制台留痕便于排查；不外发（私有仓库，注意脱敏）
    console.error("[ErrorBoundary] 渲染异常：", error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleBackHome = () => {
    window.location.href = "/tower";
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          background: "#f6f8fb",
          fontFamily:
            "system-ui,-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif",
        }}
      >
        <div style={{ maxWidth: 480, padding: 32, textAlign: "center" }}>
          <div style={{ fontSize: 48, marginBottom: 8 }}>⚠️</div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: "#0f172a", margin: "0 0 8px" }}>
            页面渲染出错
          </h2>
          <p style={{ color: "#64748b", fontSize: 14, margin: "0 0 20px" }}>
            抱歉，页面遇到了意外错误。刷新页面通常可以恢复。
          </p>
          {this.state.error && (
            <pre
              style={{
                textAlign: "left",
                background: "#fff",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                padding: 12,
                fontSize: 12,
                color: "#b91c1c",
                maxHeight: 160,
                overflow: "auto",
                margin: "0 0 20px",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {this.state.error.message}
            </pre>
          )}
          <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
            <button
              onClick={this.handleBackHome}
              style={{
                padding: "8px 18px",
                borderRadius: 8,
                border: "1px solid #cbd5e1",
                background: "#fff",
                color: "#334155",
                cursor: "pointer",
                fontSize: 14,
              }}
            >
              回到控制塔
            </button>
            <button
              onClick={this.handleReload}
              style={{
                padding: "8px 18px",
                borderRadius: 8,
                border: "none",
                background: "linear-gradient(135deg,#3370ff,#22b8cf)",
                color: "#fff",
                cursor: "pointer",
                fontSize: 14,
                fontWeight: 600,
              }}
            >
              刷新页面
            </button>
          </div>
        </div>
      </div>
    );
  }
}
