import {Easing, Interactive, interpolate, useCurrentFrame} from "remotion";
import {HEADER_HEIGHT} from "./layout";

type SceneHeaderProps = {
  eyebrow: string;
  title: string;
  accent: string;
  fadeIn?: boolean;
};

export const SceneHeader: React.FC<SceneHeaderProps> = ({eyebrow, title, accent, fadeIn = true}) => {
  const frame = useCurrentFrame();

  return (
    <Interactive.Div
      name="Scene header"
      style={{
        position: "absolute",
        left: 88,
        right: 88,
        top: 0,
        height: HEADER_HEIGHT,
        display: "flex",
        alignItems: "center",
        gap: 30,
        opacity: fadeIn ? interpolate(frame, [0, 14], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}) : 1,
      }}
    >
      <div
        style={{
          flexShrink: 0,
          padding: "11px 22px",
          borderRadius: 999,
          color: accent,
          fontSize: 26,
          fontWeight: 760,
          letterSpacing: 1.4,
          whiteSpace: "nowrap",
          backgroundColor: "rgba(5,20,37,.72)",
          border: `1px solid ${accent}66`,
        }}
      >
        {eyebrow}
      </div>
      <div
        style={{
          color: "white",
          fontSize: 50,
          fontWeight: 760,
          letterSpacing: -0.5,
          textShadow: "0 4px 20px rgba(0,0,0,.55)",
          opacity: fadeIn ? interpolate(frame, [4, 22], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1)}) : 1,
          translate: fadeIn ? interpolate(frame, [4, 22], ["0px 16px", "0px 0px"], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 200})}) : "0px 0px",
        }}
      >
        {title}
      </div>
      <div style={{marginLeft: "auto", flexShrink: 0, width: 130, height: 6, borderRadius: 99, backgroundColor: accent, boxShadow: `0 0 26px ${accent}`}} />
    </Interactive.Div>
  );
};
