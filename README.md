# LabMemory 演示视频（成片）

按《LabMemory Demo 视频录制脚本（操作手册）》+ 《LabMemory Demo 视频剪辑脚本（字幕与画面重点）》剪辑 80s 成片。

## 最终交付文件

| 文件 | 时长 | 大小 | 内容 |
|---|---|---|---|
| `LabMemory-Demo-FINAL-有配音.mp4` | 83.0s | 11.2 MB | **完整版**：干净字幕 + edge-tts XiaoxiaoNeural 自然女声配音 |
| `LabMemory-Demo-原视频剪辑.mp4` | 83.0s | 9.9 MB | 原始剪辑版（仅 11 段拼接，无字幕/无配音/无视觉增强） |
| `voiceover.txt` | - | - | 完整配音脚本（中文女声 XiaoxiaoNeural） |

## 技术规格

- 分辨率：1920×1080（16:9）
- 帧率：30fps
- 视频编码：H.264 (libx264, crf 20)
- 音频编码：AAC 128kbps（edge-tts XiaoxiaoNeural atempo 1.068x 微调到 83s）
- 文件大小：< 200MB（脚本上限）

## 视频时间线（83s，11 段）

| 段 | 区间 | 时长 | 视频素材 | 内容 |
|---|---|---|---|---|
| 0 | 0-2s | 2s | 自制 | title card（深蓝底） |
| 飞书 | 2-7s | 5s | 视频 2 [7, 12] | 飞书实验记录中枢文档 |
| 1 | 7-14s | 7s | 视频 1 [0, 13] | 工作台 |
| 2 | 14-22s | 8s | 视频 1 [20, 30] | 实验列表 |
| 3 | 22-31s | 9s | 视频 1 [40, 80] | 实验护照·任务执行 |
| 4 | 31-41s | 10s | 视频 1 [110, 130] | 任务详情→模态框→反馈（重点一）|
| 5 | 41-49s | 8s | 视频 1 [131, 158] | 主张详情 |
| 6 | 49-59s | 10s | 视频 1 [159, 170] | 实验护照·会签（重点二）|
| 7 | 59-73s | 14s | 视频 1 [80, 105] | 主张对比表（重点三）|
| 8 | 73-77s | 4s | 视频 1 [40, 80] | 实验护照·任务执行 |
| 9 | 77-83s | 6s | 视频 1 [180, 189] | 可信问答 + 6 段检索链路 |

## 视觉风格

- **字幕**：纯白色文字 + 3px 黑色描边，叠加在画面底部居中，**无任何背景框**
- **角标**：浅色（白底）+ 深蓝文字，胶囊形状，左上角对齐
- **视觉增强**：无（取消之前的红/蓝/黄 drawbox 框线）
- **配音**：edge-tts 微软在线中文女声 XiaoxiaoNeural，温暖自然

## 中间产物

- `assets/` — title card + 9 张字幕 PNG + 10 张角标 PNG + `make_clean_assets.py`（生成脚本）
- `clips/` — 11 段原始切片（含飞书过场）
- `clips_done/` — 11 段加好字幕/角标的成品片段
- `scripts/cut_final.sh` — 切片脚本（含 setpts PTS/N 加速）
- `scripts/compose_clean.sh` — 单镜头合成脚本
- `scripts/concat_clean_list.txt` — concat 列表

## 与脚本的差异（视频 1 实际素材限制）

| 镜 | 脚本期望画面 | 实际素材 | 状态 |
|---|---|---|---|
| 1 控制塔 | ✓ | 工作台 | 完美 |
| 2 会前简报 | 简报详情 | 实验列表 | ⚠️ 主题近似 |
| 3 决策编译 | 三栏对比 + 置信度 | 实验护照·任务执行 | ⚠️ 缺失三栏对比 |
| 4 人只点选 | 点绿色按钮+反馈 | 任务详情+模态框+反馈 | ✓ 完美 |
| 5 版本接棒 | current/superseded | 主张详情/Schema | ⚠️ 主题近似 |
| 6 失效阻断 | 红框阻断瞬间 | 实验护照·会签 | ⚠️ 缺失红框阻断画面 |
| 7 五态判定 | partially_supported 徽章 | 主张对比表 | ⚠️ 缺失五态徽章 |
| 8 数据关系链 | 五段贯通图 | 实验护照·任务执行 | ⚠️ 缺失五段图 |
| 9 可信问答 | 检索链路面板 | 可信问答完整画面 | ✓ 完美 |

视频 1 中确实缺失的画面（红色阻断、五态判定、五段贯通图、三栏对比置信度）在多次 2fps 抽帧扫描后确认不存在。

## 重做流程

如需调整某镜的素材或时长：

```bash
# 1. 编辑 scripts/cut_final.sh 改对应镜的 start/dur/factor
# 2. 重新切片
./scripts/cut_final.sh
# 3. 重新合成（加字幕/角标）
./scripts/compose_clean.sh
# 4. concat + 加配音
ffmpeg -y -f concat -safe 0 -i scripts/concat_clean_list.txt -i voice_edge.wav \
  -map 0:v -map 1:a \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 128k -shortest "LabMemory-Demo-FINAL-有配音.mp4"
# 5. 原视频版本（仅拼接）
ffmpeg -y -f concat -safe 0 -i scripts/concat_clean_list.txt \
  -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -an \
  "LabMemory-Demo-原视频剪辑.mp4"
```