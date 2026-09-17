import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from "remotion";
import {SceneHeader} from "../SceneHeader";

export const VersionScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: "radial-gradient(circle at 50% 20%, rgba(57,134,255,.2), transparent 38%), #071426"}}>
      <SceneHeader eyebrow="流程说明 · 版本接棒" title="新版本生效，历史仍然可追溯" accent="#8CB4FF" />
      <div style={{position: "absolute", left: 220, right: 220, top: 372, display: "flex", alignItems: "center", justifyContent: "center", gap: 80}}>
        <div style={{width: 520, padding: 48, borderRadius: 30, background: "rgba(255,255,255,.055)", border: "1px solid rgba(255,255,255,.15)", opacity: interpolate(frame, [0, 20], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>
          <div style={{fontSize: 24, color: "#A9B9C8", fontWeight: 700}}>v1 · 历史版本</div><div style={{marginTop: 48, fontSize: 64, color: "#E8EFF5", fontWeight: 750}}>80℃</div><div style={{marginTop: 54, display: "inline-block", padding: "10px 18px", borderRadius: 999, color: "#BFCAD4", backgroundColor: "rgba(255,255,255,.08)", fontSize: 24}}>只读留痕</div>
        </div>
        <div style={{fontSize: 76, color: "#8CB4FF", opacity: interpolate(frame, [18, 38], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}), translate: interpolate(frame, [18, 38], ["-25px 0px", "0px 0px"], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 180})})}}>→</div>
        <div style={{width: 520, padding: 48, borderRadius: 30, background: "linear-gradient(145deg, rgba(72,139,255,.2), rgba(74,229,182,.12))", border: "1px solid rgba(115,245,184,.62)", boxShadow: "0 28px 90px rgba(42,137,255,.22)", opacity: interpolate(frame, [28, 52], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}), scale: interpolate(frame, [28, 52], [0.94, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 190}), output: "perceptual-scale"})}}>
          <div style={{fontSize: 24, color: "#9DEECD", fontWeight: 800}}>v2 · 当前有效</div><div style={{marginTop: 48, fontSize: 64, color: "white", fontWeight: 760}}>70℃</div><div style={{marginTop: 54, display: "inline-block", padding: "10px 18px", borderRadius: 999, color: "#73F5B8", backgroundColor: "rgba(115,245,184,.12)", fontSize: 24}}>已生效</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
