#!/bin/bash
# 从演示视频源素材抽取各模块最终状态的界面截图（裁剪参数与 demo/scripts/prep_remotion_media.sh 一致）
set -e
SRC="/Users/wangjianjun/me/LabMemory/demo/remotion/public/media/source"
OUT="/Users/wangjianjun/me/LabMemory/scripts/case-h5/frames"
mkdir -p "$OUT"

BROWSER_CROP="crop=1665:805:130:140"
FEISHU_CROP="crop=1667:806:128:60"

# name:视频:截图时间点(秒)
extract() {
    local name=$1 crop=$2 t=$3
    ffmpeg -y -hide_banner -loglevel error -ss "$t" -i "$SRC/$name.mp4" \
        -vf "$crop,scale=1200:-1" -frames:v 1 -q:v 3 "$OUT/$name.jpg"
    echo "$name.jpg  $(stat -f%z "$OUT/$name.jpg") bytes"
}

extract feishu    "$FEISHU_CROP"  4.2
extract tower     "$BROWSER_CROP" 6.2
extract briefing  "$BROWSER_CROP" 7.2
extract confirm   "$BROWSER_CROP" 9.0
extract qa        "$BROWSER_CROP" 5.2
