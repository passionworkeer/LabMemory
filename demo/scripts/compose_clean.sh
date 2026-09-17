#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$DEMO_DIR"
mkdir -p clips_done
rm -f clips_done/*.mp4

compose() {
    local clip="$1" dur="$2" sub="$3" badge="$4" output="$5"
    if [ "$sub" = "-" ]; then
        cp "$clip" "$output"
    else
        ffmpeg -y -hide_banner -loglevel warning \
            -i "$clip" \
            -loop 1 -framerate 30 -t "$dur" -i "$sub" \
            -loop 1 -framerate 30 -t "$dur" -i "$badge" \
            -filter_complex "[0:v][1:v]overlay=0:H-h[v];[v][2:v]overlay=30:30" \
            -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 -an "$output"
    fi
}

compose clips/00_title.mp4       2 -                          -                              clips_done/00_title.mp4
compose clips/feishu.mp4         5 assets/sub_feishu.png      assets/badge_feishu.png        clips_done/feishu.mp4
compose clips/01_tower.mp4       7 assets/sub_01.png          assets/badge_01.png            clips_done/01_tower.mp4
compose clips/02_briefing.mp4    8 assets/sub_02.png          assets/badge_02.png            clips_done/02_briefing.mp4
compose clips/03_compile.mp4     9 assets/sub_03.png          assets/badge_03.png            clips_done/03_compile.mp4
compose clips/04_confirm.mp4    10 assets/sub_04.png          assets/badge_04.png            clips_done/04_confirm.mp4
compose clips/05_version.mp4     8 assets/sub_05.png          assets/badge_05.png            clips_done/05_version.mp4
compose clips/06_block.mp4      10 assets/sub_06.png          assets/badge_06.png            clips_done/06_block.mp4
compose clips/07_derive.mp4     14 assets/sub_07.png          assets/badge_07.png            clips_done/07_derive.mp4
compose clips/08_relation.mp4    4 -                          assets/badge_05.png            clips_done/08_relation.mp4
compose clips/09_qa.mp4          6 assets/sub_09.png          assets/badge_09.png            clips_done/09_qa.mp4

echo "=== clean shots composed ==="
ls -la clips_done
