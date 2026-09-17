import {Video} from "@remotion/media";
import {AbsoluteFill, Easing, interpolate, staticFile, useCurrentFrame} from "remotion";
import {SceneHeader} from "../SceneHeader";
import {CONTENT_HEIGHT, CONTENT_TOP} from "../layout";

export const TraceScene: React.FC = () => {
  const frame = useCurrentFrame();
  const cards = [
    ["01", "妙记原话", "“温度调整至 70℃，复验后确认”", "#68E5FF"],
    ["02", "AI 候选", "提取参数变更 · 置信度 92%", "#C5A3FF"],
    ["03", "人工确认", "保留证据位置 · 发布为当前版本", "#73F5B8"],
  ];

  return (
    <AbsoluteFill style={{backgroundColor: "#071426", overflow: "hidden"}}>
      <Video src={staticFile("media/fit/trace.mp4")} muted loop playbackRate={0.35} style={{position: "absolute", left: 0, top: CONTENT_TOP, width: "100%", height: CONTENT_HEIGHT, opacity: 0.16, filter: "blur(2px)", scale: 1.06}} />
      <div style={{position: "absolute", inset: 0, background: "linear-gradient(120deg, rgba(5,18,34,.98), rgba(9,36,62,.9))"}} />
      <SceneHeader eyebrow="真实数据结构 · 三值留痕" title="从原话到确认，每一步都有出处" accent="#8CB4FF" />
      <div style={{position: "absolute", left: 92, right: 92, top: 350, display: "flex", gap: 28}}>
        {cards.map(([index, title, text, color], cardIndex) => (
          <div key={index} style={{flex: 1, minHeight: 400, padding: "42px 36px", borderRadius: 28, background: "rgba(15,43,72,.92)", border: `1px solid ${color}66`, boxShadow: "0 28px 65px rgba(0,0,0,.28)", opacity: interpolate(frame, [8 + cardIndex * 16, 28 + cardIndex * 16], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}), translate: interpolate(frame, [8 + cardIndex * 16, 34 + cardIndex * 16], ["0px 36px", "0px 0px"], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 190})})}}>
            <div style={{fontSize: 25, fontWeight: 800, color}}>{index}</div>
            <div style={{marginTop: 58, fontSize: 46, color: "white", fontWeight: 720}}>{title}</div>
            <div style={{marginTop: 28, fontSize: 31, lineHeight: 1.55, color: "rgba(227,240,252,.72)"}}>{text}</div>
          </div>
        ))}
      </div>
      <div style={{position: "absolute", right: 92, bottom: 250, padding: "12px 22px", borderRadius: 999, color: "#73F5B8", backgroundColor: "rgba(115,245,184,.11)", border: "1px solid rgba(115,245,184,.4)", fontSize: 26, fontWeight: 730}}>证据可定位</div>
    </AbsoluteFill>
  );
};
