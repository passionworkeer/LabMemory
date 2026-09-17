import {Video} from "@remotion/media";
import {AbsoluteFill, interpolate, staticFile, useCurrentFrame} from "remotion";
import {SceneHeader} from "../SceneHeader";
import {CONTENT_HEIGHT, CONTENT_TOP} from "../layout";

type ScreenSceneProps = {
  video: string;
  eyebrow: string;
  title: string;
  accent: string;
  playbackRate: number;
  trimBefore?: number;
};

// 录屏素材已由 scripts/prep_remotion_media.sh 裁成 1920x928，与画面区域完全一致。
// 不叠加缩放与位移：任何放大会连带裁掉界面边缘，产品演示优先保证界面完整可读。
export const ScreenScene: React.FC<ScreenSceneProps> = ({video, eyebrow, title, accent, playbackRate, trimBefore = 0}) => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{background: "linear-gradient(145deg, #071426, #0C2038)", overflow: "hidden"}}>
      <div style={{position: "absolute", left: 0, top: CONTENT_TOP, width: "100%", height: CONTENT_HEIGHT, overflow: "hidden", backgroundColor: "#050F1E"}}>
        <Video
          name="Product recording"
          src={staticFile(video)}
          muted
          loop
          playbackRate={playbackRate}
          trimBefore={trimBefore}
          style={{width: "100%", height: "100%"}}
        />
      </div>
      <div style={{position: "absolute", left: 0, top: CONTENT_TOP, width: "100%", height: 30, background: "linear-gradient(180deg, rgba(7,20,38,.7), transparent)", opacity: interpolate(frame, [0, 12], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}} />
      <div style={{position: "absolute", left: 0, bottom: 0, width: "100%", height: 300, background: "linear-gradient(180deg, transparent, rgba(4,17,31,.82))"}} />
      <SceneHeader eyebrow={eyebrow} title={title} accent={accent} />
    </AbsoluteFill>
  );
};
