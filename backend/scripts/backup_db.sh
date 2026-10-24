#!/usr/bin/env bash
# 数据库备份（custom 格式）：带时间戳、校验可读性、按保留份数轮转。
# 用法：POSTGRES_CONNECTION_STRING=... BACKUP_DIR=/data/backups ./scripts/backup_db.sh
set -euo pipefail

: "${POSTGRES_CONNECTION_STRING:?需要设置 POSTGRES_CONNECTION_STRING}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${BACKUP_KEEP:-7}"

mkdir -p "$BACKUP_DIR"
stamp="$(date +%Y%m%d_%H%M%S)"
out="$BACKUP_DIR/xianzhi_${stamp}.dump"

pg_dump --format=custom --no-owner --no-privileges \
  --file "$out" "$POSTGRES_CONNECTION_STRING"

# 目录项能列出来才算完整备份（截断的 dump 通常在这里就失败）
pg_restore --list "$out" > /dev/null
sha256sum "$out" | awk '{print $1}' > "$out.sha256"

# 只保留最近 KEEP 份；点名删除比 glob 通配更安全
ls -1t "$BACKUP_DIR"/xianzhi_*.dump 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
  rm -f "$old" "$old.sha256"
done

echo "backup ok: $out ($(du -h "$out" | cut -f1))"
