#!/usr/bin/env bash
# 恢复演练：把备份恢复到独立演练库，核对关键表行数与迁移版本，不接触生产库。
# 用法：POSTGRES_CONNECTION_STRING=<源库> ./scripts/restore_drill.sh <dump> <演练库 DSN>
set -euo pipefail

DUMP="${1:?用法: restore_drill.sh <dump 文件> <演练库连接串>}"
DRILL_DSN="${2:?需要演练库连接串（必须是独立库）}"
: "${POSTGRES_CONNECTION_STRING:?需要 POSTGRES_CONNECTION_STRING 作为源库对比}"

if [ "$POSTGRES_CONNECTION_STRING" = "$DRILL_DSN" ]; then
  echo "演练库不能与源库相同" >&2
  exit 2
fi

# 演练库需事先建好（含 pgvector 扩展）；--clean 保证可反复演练
pg_restore --clean --if-exists --no-owner --no-privileges -d "$DRILL_DSN" "$DUMP"

fail=0
for table in users message_store cases chart_verdicts report_tasks app_config admin_accounts; do
  src="$(psql "$POSTGRES_CONNECTION_STRING" -tAc "select count(*) from $table")"
  dst="$(psql "$DRILL_DSN" -tAc "select count(*) from $table")"
  if [ "$src" != "$dst" ]; then
    echo "行数不一致 $table：源 $src / 演练 $dst" >&2
    fail=1
  else
    echo "$table: $dst"
  fi
done

version="$(psql "$DRILL_DSN" -tAc "select version_num from alembic_version")"
echo "迁移版本: $version"

if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "restore drill ok"
