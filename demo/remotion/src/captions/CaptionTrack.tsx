import type {Caption} from "@remotion/captions";
import {useCallback, useEffect, useState} from "react";
import {AbsoluteFill, Easing, interpolate, staticFile, useCurrentFrame, useDelayRender, useVideoConfig} from "remotion";

export const CaptionTrack: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const [captions, setCaptions] = useState<Caption[] | null>(null);
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => delayRender("Loading captions"));

  const loadCaptions = useCallback(async () => {
    try {
      const response = await fetch(staticFile("data/captions.json"));
      if (!response.ok) {
        throw new Error(`Failed to load captions: ${response.status}`);
      }
      setCaptions(await response.json());
      continueRender(handle);
    } catch (error) {
      cancelRender(error instanceof Error ? error : new Error(String(error)));
    }
  }, [cancelRender, continueRender, handle]);

  useEffect(() => {
    loadCaptions();
  }, [loadCaptions]);

  if (!captions) {
    return null;
  }

  const timeMs = (frame / fps) * 1000;
  const activeCaption = captions.find((caption) => caption.startMs <= timeMs && caption.endMs > timeMs);
  if (!activeCaption) {
    return null;
  }
  const localFrame = frame - (activeCaption.startMs / 1000) * fps;

  return (
    <AbsoluteFill style={{pointerEvents: "none", justifyContent: "flex-end", alignItems: "center", paddingBottom: 76}}>
      <div style={{maxWidth: 1500, padding: "17px 30px 19px", borderRadius: 18, backgroundColor: "rgba(3,13,25,.82)", border: "1px solid rgba(255,255,255,.16)", boxShadow: "0 12px 38px rgba(0,0,0,.38)", color: "white", fontSize: 42, fontWeight: 620, lineHeight: 1.3, letterSpacing: 0.5, textAlign: "center", opacity: interpolate(localFrame, [0, 8], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1)}), translate: interpolate(localFrame, [0, 10], ["0px 12px", "0px 0px"], {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.spring({damping: 200})})}}>{activeCaption.text}</div>
    </AbsoluteFill>
  );
};
