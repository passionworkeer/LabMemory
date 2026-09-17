import {Composition} from "remotion";
import {LabMemoryVideo} from "./LabMemoryVideo";

export const MyComposition = () => {
  return (
    <Composition
      id="LabMemoryDemoV2"
      component={LabMemoryVideo}
      durationInFrames={2490}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
