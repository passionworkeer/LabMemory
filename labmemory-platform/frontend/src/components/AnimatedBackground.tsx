// 动态海洋背景：三层缓慢漂移的 aurora 光斑 + 渐隐网格，纯 CSS 动画零 JS 开销
export default function AnimatedBackground({ strong = false }: { strong?: boolean }) {
  return (
    <div className={`app-bg${strong ? " strong" : ""}`} aria-hidden="true">
      <div className="blob blob-1" />
      <div className="blob blob-2" />
      <div className="blob blob-3" />
      <div className="grid-overlay" />
    </div>
  );
}
