# LabMemory 演示视频

## 当前成片

[`LabMemory-Demo-V3-成片.mp4`](./LabMemory-Demo-V3-成片.mp4) — 83 秒、1920×1080、30fps，使用系统预置研发数据的全流程真实演示。

这一版解决的具体问题：

- **画面切点按配音的真实语音边界排列**。原版旁白还在介绍产品时画面已经切进飞书，控制塔旁白讲到一半画面就切走了；重新按语音边界划成 11 个场景后，画面与解说逐句对应。
- **标题带与画面分离**。标题、角标排在画面区上方的独立标题带里，不再叠在界面文字上。原版标题直接压在录屏内容上，与页面自身文字重叠。
- **去掉录屏里的无关区域**。macOS 菜单栏、浏览器标签栏、地址栏、Dock 与桌面留白全部裁掉，产品界面按 1:1 铺满画面区。原版浏览器工具栏和 Dock 占掉大量画面，操作细节被压到看不清。
- **字幕进入安全区并放大到 42px**。原版字幕字号偏小且压在 Dock 上。
- **区分"真实操作"与"流程说明"**。录屏里没有直接画面的三项能力用流程图表达并标注"流程说明"，有录屏的场景标注"真实操作"，不把图解当成功能实录。

## 版本对照

| 文件 | 说明 |
|---|---|
| `LabMemory-Demo-V3-成片.mp4` | **当前成片**，Remotion 工程渲染，音画对齐、版式统一 |
| `LabMemory-Demo-V2-优化版.mp4` | 上一版，已被 V3 取代：标题与录屏内容重叠、浏览器工具栏未裁掉（保留在本地供对比，未入库） |
| `LabMemory-Demo-FINAL-有配音.mp4` | 原始剪辑版：11 段 FFmpeg 拼接 + 字幕 + edge-tts 配音 |
| `LabMemory-Demo-原视频剪辑.mp4` | 原始拼接版：仅 11 段拼接，无字幕无配音 |

## 技术规格

- 分辨率 1920×1080（16:9），帧率 30fps
- 视频编码 H.264（libx264, crf 18），音频编码 AAC
- 配音：edge-tts 中文女声 XiaoxiaoNeural，atempo 1.068x 微调到 83s
- 配音是时间主轴，画面和字幕都以它的语音边界为准

## 时间线（83 秒，11 个场景）

| 场景 | 区间 | 画面 | 角标 |
|---|---|---|---|
| 01 品牌与三处重点 | 0.0–11.5s | 标题卡 + 三张重点卡片 | 无 |
| 02 飞书会议接入 | 11.5–16.4s | 录屏：飞书会议消息与待复核任务 | 真实操作 |
| 03 研发控制塔 | 16.4–28.0s | 录屏：四条待复核会议 | 真实操作 |
| 04 会前研讨包 | 28.0–38.6s | 录屏：参数、版本与来源 | 真实操作 |
| 05 三值留痕 | 38.6–46.3s | 图解：妙记原话 → AI 候选 → 人工确认 | 真实数据结构 |
| 06 人工一次点选 | 46.3–51.1s | 录屏：AI 给候选，人做决定 | 真实操作 |
| 07 版本接棒 | 51.1–55.6s | 图解：v1 只读留痕，v2 当前有效 | 流程说明 |
| 08 失效版本阻断 | 55.6–62.5s | 图解：引用失效版本被拦截与修正 | 流程说明 |
| 09 部分支持派生 | 62.5–68.4s | 图解：部分支持 → 下一轮复验任务 | 流程说明 |
| 10 五段状态贯通 | 68.4–78.1s | 图解：复核、主张、任务、审计、结果 | 流程说明 |
| 11 可信问答 | 78.1–83.0s | 录屏：答案与证据出处同屏 | 真实操作 |

## 重新制作

成片由 [`remotion/`](./remotion/) 工程渲染，见 [remotion/README.md](./remotion/README.md)：

```console
cd remotion
npm install
npm run prep      # 由 media/source 生成 media/fit（需要 ffmpeg）
npm run render    # 输出 LabMemory-Demo-V3-成片.mp4
```

## 为什么有三段流程图

录屏素材（视频 1，40 秒的控制塔全流程）里确实不存在以下画面，2fps 抽帧扫描确认过：

- 引用失效版本被红框阻断的瞬间
- `partially_supported` 五态判定徽章
- 五段状态贯通图

所以这三项能力用流程图说明并标注"流程说明"，不用主题相近的录屏冒充功能实录。以下镜次在录屏里有对应画面但主题只是近似，角标仍标"真实操作"，因为它们确实是真实界面：

| 镜次 | 需要的画面 | 录屏实际内容 |
|---|---|---|
| 02 会前简报 | 简报详情 | 实验列表 |
| 07 版本接棒 | current/superseded 对比 | 主张详情 / Schema |

## 旧版 FFmpeg 剪辑流程（备用）

V3 之前的成片由脚本直接拼接，保留备用。中间产物与脚本：

- `clips/` — 11 段原始切片（含飞书过场）
- `clips_done/` — 11 段加好字幕与角标的成品片段
- `assets/` — title card、字幕 PNG、角标 PNG 与生成脚本 `make_clean_assets.py`
- `scripts/cut_final.sh` — 切片脚本（含 setpts PTS/N 加速）
- `scripts/compose_clean.sh` — 单镜头合成脚本
- `scripts/concat_clean_list.txt` — concat 列表

重新拼接：

```bash
./scripts/cut_final.sh      # 从桌面录屏切片
./scripts/compose_clean.sh  # 叠加字幕与角标
ffmpeg -y -f concat -safe 0 -i scripts/concat_clean_list.txt -i voice_edge.wav \
  -map 0:v -map 1:a -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 128k -shortest "LabMemory-Demo-FINAL-有配音.mp4"
```

`voice_edge.wav` 是配音中间件，不在仓库里。需要时用 edge-tts 重新生成，再按 83 秒目标时长用 atempo 微调：

```bash
edge-tts --voice zh-CN-XiaoxiaoNeural --text "$(cat voiceover.txt)" --write-media voice.mp3
ffmpeg -y -i voice.mp3 -filter:a "atempo=1.068" voice_edge.wav
```

这套流程的切片路径写死了桌面录屏文件名（`scripts/cut_final.sh` 顶部的 `SRC1`/`SRC2`），录屏文件不在仓库里，换机器需要改路径。V3 之后的修改建议直接改 Remotion 工程。

## 配音脚本

`voiceover.txt` 是完整配音文本（中文女声 XiaoxiaoNeural）。改动配音后，`remotion/public/data/captions.json` 的字幕时间码与 `remotion/src/LabMemoryVideo.tsx` 的场景边界都要同步更新。
