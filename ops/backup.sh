#!/usr/bin/env bash
# IIC daily backup — SQLite + Redis AOF.
#
# Cron entry (root):
#   0 3 * * *  /opt/iic/ops/backup.sh >> /var/log/iic/backup.log 2>&1
set -euo pipefail

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_ROOT=${BACKUP_ROOT:-/var/backups/iic}
SQLITE_DB=${IIC_DB_PATH:-$HOME/.tradingagents/iic.db}
REDIS_AOF=${REDIS_AOF:-/var/lib/redis/appendonly.aof}

mkdir -p "$BACKUP_ROOT/sqlite" "$BACKUP_ROOT/redis"

# SQLite: use the dedicated .backup pragma; safe under concurrent writers.
sqlite3 "$SQLITE_DB" ".backup '$BACKUP_ROOT/sqlite/iic-$STAMP.db'"

# Redis: ask the server to rewrite its AOF, then snapshot the file.
redis-cli BGREWRITEAOF
sleep 5
cp "$REDIS_AOF" "$BACKUP_ROOT/redis/appendonly-$STAMP.aof"

# Retain last 14 days.
find "$BACKUP_ROOT/sqlite" -name 'iic-*.db' -mtime +14 -delete
find "$BACKUP_ROOT/redis"  -name 'appendonly-*.aof' -mtime +14 -delete

echo "backup complete: $STAMP"
