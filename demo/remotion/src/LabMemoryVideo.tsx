import {Audio} from "@remotion/media";
import {AbsoluteFill, Sequence, staticFile} from "remotion";
import {CaptionTrack} from "./captions/CaptionTrack";
import {BlockScene} from "./scenes/BlockScene";
import {ChainScene} from "./scenes/ChainScene";
import {DeriveScene} from "./scenes/DeriveScene";
import {IntroScene} from "./scenes/IntroScene";
import {ScreenScene} from "./scenes/ScreenScene";
import {TraceScene} from "./scenes/TraceScene";
import {VersionScene} from "./scenes/VersionScene";

export const LabMemoryVideo: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: "#071426", fontFamily: '"PingFang SC", "Microsoft YaHei", sans-serif'}}>
      <Sequence name="01 品牌与三处重点" durationInFrames={344}>
        <IntroScene />
      </Sequence>
      <Sequence name="02 飞书会议接入" from={344} durationInFrames={147}>
        <ScreenScene video="media/fit/feishu.mp4" eyebrow="真实操作 · 飞书" title="会议结束，待复核任务自动就位" accent="#68E5FF" playbackRate={1} />
      </Sequence>
      <Sequence name="03 研发控制塔" from={491} durationInFrames={348}>
        <ScreenScene video="media/fit/tower.mp4" eyebrow="真实操作 · 控制塔" title="四条待复核会议，一屏掌握" accent="#73F5B8" playbackRate={0.6} />
      </Sequence>
      <Sequence name="04 会前研讨包" from={839} durationInFrames={318}>
        <ScreenScene video="media/fit/briefing.mp4" eyebrow="真实操作 · 会前研讨包" title="参数、版本与来源同时可见" accent="#8CB4FF" playbackRate={0.75} />
      </Sequence>
      <Sequence name="05 三值留痕" from={1157} durationInFrames={233}>
        <TraceScene />
      </Sequence>
      <Sequence name="06 人工一次点选" from={1390} durationInFrames={142}>
        <ScreenScene video="media/fit/confirm.mp4" eyebrow="真实操作 · 人工确认" title="AI 给候选，人做最终决定" accent="#77E6A4" playbackRate={1} trimBefore={120} />
      </Sequence>
      <Sequence name="07 版本接棒说明" from={1532} durationInFrames={137}>
        <VersionScene />
      </Sequence>
      <Sequence name="08 失效版本阻断说明" from={1669} durationInFrames={207}>
        <BlockScene />
      </Sequence>
      <Sequence name="09 部分支持派生说明" from={1876} durationInFrames={177}>
        <DeriveScene />
      </Sequence>
      <Sequence name="10 五段状态贯通" from={2053} durationInFrames={290}>
        <ChainScene />
      </Sequence>
      <Sequence name="11 可信问答" from={2343} durationInFrames={147}>
        <ScreenScene video="media/fit/qa.mp4" eyebrow="真实操作 · 可信问答" title="答案与证据出处同屏呈现" accent="#C5A3FF" playbackRate={1} />
      </Sequence>
      <CaptionTrack />
      <Audio src={staticFile("audio/voiceover.m4a")} />
    </AbsoluteFill>
  );
};
