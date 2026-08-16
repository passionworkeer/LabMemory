#!/bin/bash
# SQLite 每日在线备份（.backup API，不 cp 活库）；保留最近 7 份
set -euo pipefail

DB="/home/admin/labmemory/labmemory-platform/data/labmemory.db"
DEST_DIR="/home/admin/labmemory/backups"
KEEP=7
STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="$DEST_DIR/labmemory_$STAMP.db"

mkdir -p "$DEST_DIR"

# Python stdlib sqlite3 backup API —— 与官方 sqlite3 CLI 的 .backup 等价
/home/admin/labmemory/.venv/bin/python - "$DB" "$DEST" <<'PYEOF'
import sqlite3, sys
src_path, dst_path = sys.argv[1], sys.argv[2]
src = sqlite3.connect(src_path)
dst = sqlite3.connect(dst_path)
try:
    src.backup(dst)  # 在线备份，可安全用于运行中的库
finally:
    dst.close()
    src.close()
PYEOF

# 完整性校验后轮转（integrity_check 返回 ok 才保留）
if /home/admin/labmemory/.venv/bin/python -c "
import sqlite3, sys
db = sqlite3.connect('$DEST')
ok = db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
db.close()
sys.exit(0 if ok else 1)
"; then
    echo "$(date '+%F %T') 备份成功: $DEST"
else
    echo "$(date '+%F %T') 备份损坏，删除: $DEST" >&2
    rm -f "$DEST"
    exit 1
fi

# 只保留最近 KEEP 份
ls -1t "$DEST_DIR"/labmemory_*.db 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "$(date '+%F %T') 当前备份数: $(ls -1 "$DEST_DIR"/labmemory_*.db | wc -l)"
