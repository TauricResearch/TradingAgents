#!/usr/bin/env bash
# IIC daily backup — SQLite + Redis AOF.
#
# On this host Redis runs as the Docker container `iic-redis`
# (host volume /srv/iic/redis -> /data in-container; Redis 7 uses a
# multi-file AOF under appendonlydir/). There is no host redis-cli and no
# /var/lib/redis, so the rewrite is issued *inside* the container and the
# AOF is pulled from the docker volume.
#
# Cron entry (run as ziwei-huang, or as root — paths are absolute either way):
#   0 3 * * *  /home/ziwei-huang/TradingAgents/TradingAgents/ops/backup.sh \
#                >> /home/ziwei-huang/TradingAgents/TradingAgents/logs/backup.log 2>&1
set -euo pipefail

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_ROOT=${BACKUP_ROOT:-/var/backups/iic}
# Pin the SQLite path; do NOT rely on $HOME (cron/root would resolve it wrong).
SQLITE_DB=${IIC_DB_PATH:-/home/ziwei-huang/.tradingagents/iic.db}
# Host-side mount of the container's /data volume.
REDIS_VOLUME=${REDIS_VOLUME:-/srv/iic/redis}
REDIS_CONTAINER=${REDIS_CONTAINER:-iic-redis}

mkdir -p "$BACKUP_ROOT/sqlite" "$BACKUP_ROOT/redis"

# SQLite: use the dedicated .backup pragma; safe under concurrent writers.
sqlite3 "$SQLITE_DB" ".backup '$BACKUP_ROOT/sqlite/iic-$STAMP.db'"

# Redis: ask the server (inside the container) to rewrite its AOF, then
# snapshot the on-disk AOF state. Redis 7 keeps a multi-file appendonlydir/,
# so copy the whole /data tree out of the container.
docker exec "$REDIS_CONTAINER" redis-cli BGREWRITEAOF
sleep 5
REDIS_DEST="$BACKUP_ROOT/redis/redis-$STAMP"
mkdir -p "$REDIS_DEST"
docker cp "$REDIS_CONTAINER:/data/." "$REDIS_DEST/"

# Retain last 14 days.
find "$BACKUP_ROOT/sqlite" -name 'iic-*.db' -mtime +14 -delete
find "$BACKUP_ROOT/redis"  -maxdepth 1 -name 'redis-*' -mtime +14 -exec rm -rf {} +

echo "backup complete: $STAMP"
