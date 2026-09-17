import {AbsoluteFill, Easing, Interactive, interpolate, useCurrentFrame} from "remotion";

export const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{background: "radial-gradient(circle at 76% 18%, rgba(36,183,255,0.22), transparent 34%), radial-gradient(circle at 16% 82%, rgba(108,92,231,0.2), transparent 38%), linear-gradient(135deg, #071426 0%, #102949 56%, #071426 100%)", overflow: "hidden"}}>
      <div style={{position: "absolute", inset: 0, opacity: 0.12, backgroundImage: "linear-gradient(rgba(255,255,255,.16) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.16) 1px, transparent 1px)", backgroundSize: "72px 72px"}} />
      <Interactive.Div name="Brand mark" style={{position: "absolute", left: 116, top: 104, color: "#77E6FF", fontSize: 30, fontWeight: 700, letterSpacing: 6, opacity: interpolate(frame, [0, 18], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1)})}}>LABMEMORY · 晶研智流</Interactive.Div>
      <Interactive.Div name="Hero title" style={{position: "absolute", left: 110, top: 210, width: 1220, color: "white", fontSize: 104, lineHeight: 1.08, fontWeight: 760, letterSpacing: -3, opacity: interpolate(frame, [8, 32, 154, 178], [0, 1, 1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1)}), translate: interpolate(frame, [8, 32], ["0px 30px", "0px 0px"], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 200})})}}>让实验有证据<br />让决策可追溯</Interactive.Div>
      <Interactive.Div name="Hero subtitle" style={{position: "absolute", left: 118, top: 485, color: "rgba(229,244,255,.82)", fontSize: 42, fontWeight: 450, opacity: interpolate(frame, [24, 48, 154, 178], [0, 1, 1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>全流程真实演示 · 系统预置研发数据</Interactive.Div>
      <div style={{position: "absolute", left: 110, right: 110, top: 300, display: "flex", gap: 30, opacity: interpolate(frame, [170, 198], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 200})})}}>
        {[
          ["01", "人只点选", "AI 提供候选，人完成最终确认", "#73F5B8"],
          ["02", "失效阻断", "行动前校验当前有效版本", "#FF8E8E"],
          ["03", "部分支持派生", "结果自动衔接下一轮复验", "#C5A3FF"],
        ].map(([index, title, description, color], cardIndex) => (
          <div key={index} style={{flex: 1, minHeight: 390, padding: "46px 38px", borderRadius: 30, background: "rgba(10,31,55,.82)", border: `1px solid ${color}55`, boxShadow: "0 26px 70px rgba(0,0,0,.28)", translate: interpolate(frame, [178 + cardIndex * 8, 210 + cardIndex * 8], ["0px 34px", "0px 0px"], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 180})})}}>
            <div style={{fontSize: 28, fontWeight: 800, color}}>{index}</div>
            <div style={{marginTop: 62, fontSize: 52, color: "white", fontWeight: 720}}>{title}</div>
            <div style={{marginTop: 24, fontSize: 30, lineHeight: 1.5, color: "rgba(226,239,250,.7)"}}>{description}</div>
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
