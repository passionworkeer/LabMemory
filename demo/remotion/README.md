# LabMemory 演示成片 · Remotion 工程

`LabMemory-Demo-V3-成片.mp4` 的来源工程。83 秒、1920×1080、30fps，画面切点按配音的真实语音边界排列。

## 目录结构

```
src/
  Root.tsx              注册合成 LabMemoryDemoV2（2490 帧 = 83 秒）
  LabMemoryVideo.tsx    11 个场景的顺序、起止帧与素材绑定
  layout.ts             画面分区常量（标题带高度、画面区域、图解安全区）
  SceneHeader.tsx       统一的标题带：左侧角标 + 标题，右侧强调色短线
  captions/CaptionTrack.tsx   读取 data/captions.json，按时间码显示字幕
  scenes/
    IntroScene.tsx      00:00 品牌 + 三处重点卡片
    ScreenScene.tsx     真实录屏场景（控制塔、会前研讨包、人工确认、可信问答、飞书）
    TraceScene.tsx      三值留痕
    VersionScene.tsx    版本接棒（流程图）
    BlockScene.tsx      失效阻断（流程图）
    DeriveScene.tsx     部分支持派生（流程图）
    ChainScene.tsx      五段状态贯通（流程图）
public/
  audio/voiceover.m4a   83 秒配音（edge-tts 中文女声，时间主轴）
  data/captions.json    字幕时间码，与配音逐句对齐
  data/voiceover.json   配音脚本（含每句对应的场景）
  media/source/         录屏原始片段（从桌面录屏裁出的 5–10 秒片段）
  media/fit/            上一步的产物：裁成 1920×928 的画面画幅，渲染时使用
```

## 渲染

```console
npm install
npm run prep          # 由 media/source 生成 media/fit（需要 ffmpeg）
npm run render        # 输出 ../LabMemory-Demo-V3-成片.mp4
```

`package.json` 里的 `render` 脚本已经带好参数。等价的完整命令：

```bash
npx remotion render src/index.ts LabMemoryDemoV2 ../LabMemory-Demo-V3-成片.mp4 \
  --codec=h264 --crf=18 --concurrency=10 \
  --browser-executable='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```

`--browser-executable` 在未安装 Chrome Headless Shell 的机器上必须显式指定。14 核机器上约 4 分钟。

## 画面分区

所有场景共用 `layout.ts` 里的分区，这是避免"标题压住画面内容"的关键：

| 区域 | 纵向范围 | 内容 |
|---|---|---|
| 标题带 | 0–152 | 左：角标（真实操作／流程说明）+ 场景标题；右：强调色短线 |
| 画面区 | 152–1080 | 录屏或流程图，1920×928 |
| 字幕安全区 | 底部约 1010 以上 | 字幕条，叠加在画面之上 |

图解的卡片内容排在 230–850，不进入字幕区。改版式时只改 `layout.ts` 与对应场景文件的 `top` 值即可。

## 录屏素材处理

`media/source/` 是录屏原片，含 macOS 菜单栏、浏览器标签栏、地址栏、Dock 与桌面留白。`npm run prep`（即 `../scripts/prep_remotion_media.sh`）按固定窗口几何裁成 1920×928：

- 浏览器录制：`crop=1665:805:130:140`，去掉窗口外的桌面、顶部工具栏，底部留白由字幕条覆盖
- 飞书客户端：`crop=1667:806:128:60`，从窗口标题栏下方的消息正文开始

裁切框按窗口像素位置写死。换一台机器或改窗口大小重新录制后，需要重新测量窗口边界并更新脚本里的 `BROWSER_CROP` / `FEISHU_CROP`。

成片里不放任何缩放或位移动画：录屏按 1:1 铺满画面区，保证界面文字可读。取消缩放动画的原因见 `src/scenes/ScreenScene.tsx` 顶部注释。

## 字幕

`public/data/captions.json` 是 `{text, startMs, endMs}` 数组，`CaptionTrack` 按当前帧时间查找命中项。字幕与配音逐句对齐，改配音后需要同步更新时间码。

## 说明标注

录屏里没有直接画面的三项能力（版本接棒、失效阻断、部分支持派生）用流程图表达，角标统一写"流程说明"；有真实录屏的场景角标写"真实操作"。两者不混用，避免把图解当成功能实录。
