import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from "remotion";
import {SceneHeader} from "../SceneHeader";

export const ChainScene: React.FC = () => {
  const frame = useCurrentFrame();
  const nodes = [["01", "复核", "原始记录"], ["02", "主张", "当前结论"], ["03", "任务", "执行对象"], ["04", "审计", "行动校验"], ["05", "结果", "回流派生"]];
  return (
    <AbsoluteFill style={{background: "radial-gradient(circle at 50% 50%, rgba(57,154,255,.18), transparent 46%), #071426"}}>
      <SceneHeader eyebrow="流程说明 · 全链路追溯" title="一条实验，五段状态贯通" accent="#68E5FF" />
      <div style={{position: "absolute", left: 82, right: 82, top: 372, display: "flex", alignItems: "center", justifyContent: "space-between"}}>
        {nodes.map(([index, title, detail], nodeIndex) => (
          <div key={index} style={{display: "contents"}}>
            <div style={{width: 270, height: 320, padding: "38px 28px", borderRadius: 28, background: "linear-gradient(145deg, rgba(27,71,108,.9), rgba(12,42,70,.92))", border: "1px solid rgba(104,229,255,.42)", boxShadow: "0 22px 58px rgba(0,0,0,.25)", opacity: interpolate(frame, [nodeIndex * 22, nodeIndex * 22 + 24], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}), translate: interpolate(frame, [nodeIndex * 22, nodeIndex * 22 + 28], ["0px 32px", "0px 0px"], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 190})})}}>
              <div style={{fontSize: 22, color: "#68E5FF", fontWeight: 800}}>{index}</div><div style={{marginTop: 56, fontSize: 48, color: "white", fontWeight: 750}}>{title}</div><div style={{marginTop: 34, fontSize: 27, color: "rgba(224,241,253,.65)"}}>{detail}</div>
            </div>
            {nodeIndex < nodes.length - 1 ? <div style={{fontSize: 46, color: "#68E5FF", opacity: interpolate(frame, [nodeIndex * 22 + 18, nodeIndex * 22 + 38], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}}>→</div> : null}
          </div>
        ))}
      </div>
      <div style={{position: "absolute", left: 92, right: 92, top: 760, height: 5, borderRadius: 99, background: "linear-gradient(90deg, #68E5FF, #8CB4FF, #C5A3FF, #73F5B8)", scale: interpolate(frame, [10, 130], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1)}), transformOrigin: "left center"}} />
    </AbsoluteFill>
  );
};
