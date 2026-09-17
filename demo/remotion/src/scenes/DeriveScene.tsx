import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from "remotion";
import {SceneHeader} from "../SceneHeader";

export const DeriveScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{background: "radial-gradient(circle at 26% 24%, rgba(151,105,255,.2), transparent 38%), #071426"}}>
      <SceneHeader eyebrow="流程说明 · 结果回流" title="部分支持，不停在结论里" accent="#C5A3FF" />
      <div style={{position: "absolute", left: 220, right: 220, top: 380, display: "flex", alignItems: "center", justifyContent: "center", gap: 84}}>
        <div style={{width: 530, padding: 46, borderRadius: 30, background: "linear-gradient(145deg, rgba(141,94,255,.22), rgba(62,45,111,.5))", border: "1px solid rgba(197,163,255,.62)", opacity: interpolate(frame, [0, 20], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>
          <div style={{fontSize: 26, color: "#D9C4FF", fontWeight: 760}}>本轮实验结果</div><div style={{marginTop: 60, fontSize: 62, color: "white", fontWeight: 760}}>部分支持</div><div style={{marginTop: 34, fontSize: 30, lineHeight: 1.5, color: "rgba(236,228,255,.74)"}}>关键趋势成立，边界条件仍需复验</div>
        </div>
        <div style={{fontSize: 78, color: "#C5A3FF", opacity: interpolate(frame, [20, 44], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}), translate: interpolate(frame, [20, 44], ["-28px 0px", "0px 0px"], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 180})})}}>→</div>
        <div style={{width: 610, padding: 46, borderRadius: 30, background: "linear-gradient(145deg, rgba(31,116,91,.5), rgba(16,71,66,.72))", border: "1px solid rgba(115,245,184,.62)", boxShadow: "0 28px 90px rgba(60,235,180,.16)", opacity: interpolate(frame, [38, 65], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}), scale: interpolate(frame, [38, 65], [0.92, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 180}), output: "perceptual-scale"})}}>
          <div style={{fontSize: 26, color: "#9DEECD", fontWeight: 760}}>自动派生</div><div style={{marginTop: 54, fontSize: 54, color: "white", fontWeight: 760}}>下一轮复验任务</div><div style={{marginTop: 30, fontSize: 30, lineHeight: 1.5, color: "rgba(222,255,242,.74)"}}>带入证据、参数与未决问题</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
