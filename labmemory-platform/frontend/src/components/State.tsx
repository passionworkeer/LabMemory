// 全局加载 / 错误状态：品牌化旋转动画 + 错误卡，替换各页裸"加载中…"/红字错误
export function Loading({ label = "加载中", compact = false }: { label?: string; compact?: boolean }) {
  return (
    <div className={compact ? "state-compact" : "state"} role="status" aria-live="polite">
      <div className="state-spinner" />
      {!compact && <div className="state-text">{label}…</div>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="state state-error" role="alert">
      <div className="state-error-icon">⚠</div>
      <div className="state-error-text">{message}</div>
    </div>
  );
}
