import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from "remotion";
import {SceneHeader} from "../SceneHeader";

export const BlockScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: "radial-gradient(circle at 72% 30%, rgba(255,92,92,.16), transparent 38%), #071426"}}>
      <SceneHeader eyebrow="流程说明 · 行动前审计" title="失效版本在任务建立瞬间被拦截" accent="#FF9A9A" />
      <div style={{position: "absolute", left: 118, right: 118, top: 382, display: "flex", alignItems: "center", justifyContent: "space-between"}}>
        <div style={{width: 450, padding: 38, borderRadius: 28, backgroundColor: "rgba(24,50,78,.9)", border: "1px solid rgba(140,180,255,.35)", opacity: interpolate(frame, [0, 18], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>
          <div style={{fontSize: 26, color: "#A9C8E7"}}>拟建立任务</div><div style={{marginTop: 36, color: "white", fontSize: 48, fontWeight: 730}}>引用参数 v1</div><div style={{marginTop: 24, color: "#FFB0B0", fontSize: 29}}>80℃ · 已失效</div>
        </div>
        <div style={{fontSize: 64, color: "#8CB4FF", opacity: interpolate(frame, [16, 34], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>→</div>
        <div style={{width: 500, padding: 44, borderRadius: 30, background: "linear-gradient(145deg, rgba(110,24,38,.86), rgba(58,19,30,.92))", border: "2px solid rgba(255,114,114,.8)", boxShadow: "0 28px 90px rgba(255,68,86,.22)", opacity: interpolate(frame, [30, 55], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}), scale: interpolate(frame, [30, 55], [0.9, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 170}), output: "perceptual-scale"})}}>
          <div style={{fontSize: 28, color: "#FFB0B0", fontWeight: 800}}>操作已阻断</div><div style={{marginTop: 40, fontSize: 44, color: "white", fontWeight: 730}}>请改用当前有效版本</div><div style={{marginTop: 26, fontSize: 30, color: "rgba(255,226,229,.76)"}}>v2 · 70℃</div>
        </div>
        <div style={{fontSize: 64, color: "#73F5B8", opacity: interpolate(frame, [55, 74], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>→</div>
        <div style={{width: 380, padding: 38, borderRadius: 28, backgroundColor: "rgba(22,67,62,.78)", border: "1px solid rgba(115,245,184,.55)", opacity: interpolate(frame, [70, 94], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>
          <div style={{fontSize: 26, color: "#9DEECD"}}>修正后</div><div style={{marginTop: 36, color: "white", fontSize: 46, fontWeight: 730}}>任务可建立</div><div style={{marginTop: 24, color: "#73F5B8", fontSize: 29}}>证据链同步更新</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
