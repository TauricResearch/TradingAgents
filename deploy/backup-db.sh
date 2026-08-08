#!/usr/bin/env bash
# Nightly SQLite backup, kept for 14 days.
#
# Uses `sqlite3 .backup` rather than `cp`. The service holds the database open
# and the 60-second monitor writes to it, so a plain copy can capture a torn
# page mid-write and produce a backup that only fails when you try to restore
# it. `.backup` takes a read lock and is safe against a live writer.
#
# Install:
#   chmod +x ~/TradingAgents/deploy/backup-db.sh
#   crontab -e
#   17 4 * * *  /home/ubuntu/TradingAgents/deploy/backup-db.sh >> /home/ubuntu/backup.log 2>&1
set -euo pipefail

DB="${HOME}/.tradingagents/assistant.db"
DEST="${HOME}/backups"
KEEP_DAYS=14

[ -f "$DB" ] || { echo "$(date -Is) no database at $DB"; exit 0; }
mkdir -p "$DEST"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${DEST}/assistant-${STAMP}.db"

sqlite3 "$DB" ".backup '${OUT}'"
# Prove the copy is readable before trusting it — a backup you have never
# opened is a hope, not a backup.
sqlite3 "$OUT" "pragma integrity_check;" | head -1 | grep -q '^ok$' \
  || { echo "$(date -Is) INTEGRITY CHECK FAILED for ${OUT}"; exit 1; }

gzip -f "$OUT"
find "$DEST" -name 'assistant-*.db.gz' -mtime "+${KEEP_DAYS}" -delete

echo "$(date -Is) backed up $(du -h "${OUT}.gz" | cut -f1) -> ${OUT}.gz"
