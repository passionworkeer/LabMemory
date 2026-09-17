#!/bin/bash
# 把录屏裁成 Remotion 成片的画面画幅（1920x928），去掉 macOS 菜单栏、浏览器标签栏、
# 地址栏、Dock 与桌面留白，并让录制窗口铺满画面区域。
# 输入：public/media/source/*.mp4   输出：public/media/fit/*.mp4
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIT_DIR="$SCRIPT_DIR/../remotion/public/media/fit"
SRC_DIR="$SCRIPT_DIR/../remotion/public/media/source"

mkdir -p "$FIT_DIR"
rm -f "$FIT_DIR"/*.mp4

# 浏览器录制：窗口 x 130..1795，页面内容从 y 140 开始；底部留白与输入区裁掉（该区域被字幕条覆盖）
BROWSER_CROP="crop=1665:805:130:140"
# 飞书客户端：窗口 x 128..1795，从窗口标题栏下方的消息正文开始，裁掉底部输入框与空档
FEISHU_CROP="crop=1667:806:128:60"

# source 里的 version.mp4 当前没有任何场景使用（版本接棒用图解表达），因此不参与裁剪
for name in tower briefing confirm qa trace; do
    ffmpeg -y -hide_banner -loglevel error -i "$SRC_DIR/$name.mp4" \
        -vf "$BROWSER_CROP,scale=1920:928,fps=30,format=yuv420p" \
        -an -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 30 \
        "$FIT_DIR/$name.mp4"
    echo "裁剪 $name.mp4（浏览器）"
done

ffmpeg -y -hide_banner -loglevel error -i "$SRC_DIR/feishu.mp4" \
    -vf "$FEISHU_CROP,scale=1920:928,fps=30,format=yuv420p" \
    -an -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 30 \
    "$FIT_DIR/feishu.mp4"
echo "裁剪 feishu.mp4（飞书）"

echo "=== 画幅裁剪完成 ==="
for f in "$FIT_DIR"/*.mp4; do
    echo "  $(basename "$f"): $(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$f")"
done
