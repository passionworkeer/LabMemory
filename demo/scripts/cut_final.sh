#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC1="/Users/wangjianjun/Desktop/录屏2026-09-16 21.51.14.mov"
SRC2="/Users/wangjianjun/Desktop/录屏2026-09-16 21.56.31.mov"
TITLE="$DEMO_DIR/assets/title_card.png"
OUT="$DEMO_DIR/clips"

mkdir -p "$OUT"

clip_v1() {
    local src="$1" start="$2" dur="$3" factor="$4" name="$5"
    ffmpeg -y -hide_banner -loglevel error \
        -ss "$start" -t "$dur" -i "$src" \
        -vf "setpts=PTS/$factor,scale=-1:1080,pad=1920:1080:(1920-iw)/2:0:color=0x101c38,fps=30,format=yuv420p" \
        -an -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 \
        "$OUT/$name"
}

# 镜 0
ffmpeg -y -hide_banner -loglevel error -loop 1 -framerate 30 -i "$TITLE" -t 2 -vf "format=yuv420p" -c:v libx264 -preset veryfast -r 30 -pix_fmt yuv420p "$OUT/00_title.mp4"

# 飞书过场 v2 [7, 12]（5s 加速 1x = 5s），覆盖实验记录中枢文档 + 通知卡
ffmpeg -y -hide_banner -loglevel error -ss 7 -t 5 -i "$SRC2" \
    -vf "scale=-1:1080,pad=1920:1080:(1920-iw)/2:0:color=0x101c38,fps=30,format=yuv420p,drawbox=x=0:y=0:w=320:h=ih:color=0x101c38@0.92:t=fill,drawbox=x=1600:y=0:w=320:h=ih:color=0x101c38@0.55:t=fill" \
    -an -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 \
    "$OUT/feishu.mp4"

# 镜 1
clip_v1 "$SRC1" 0    13  1.86 "01_tower.mp4"
# 镜 2
clip_v1 "$SRC1" 20   10  1.25 "02_briefing.mp4"
# 镜 3
clip_v1 "$SRC1" 40   40  4.44 "03_compile.mp4"
# 镜 4
clip_v1 "$SRC1" 110  20  2.0  "04_confirm.mp4"
# 镜 5
clip_v1 "$SRC1" 131  27  3.38 "05_version.mp4"
# 镜 6
clip_v1 "$SRC1" 159  11  1.1  "06_block.mp4"
# 镜 7
clip_v1 "$SRC1" 80   25  1.79 "07_derive.mp4"
# 镜 8
clip_v1 "$SRC1" 40   40  10.0 "08_relation.mp4"
# 镜 9
clip_v1 "$SRC1" 180  9   1.5  "09_qa.mp4"

echo "=== final clips ready ==="
ls -la "$OUT"
