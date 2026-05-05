#!/usr/bin/env bash
# Restart the gui service without rebuilding (fast — for picking up an
# .env change or kicking a stuck process). Use upgrade.sh for code changes.
#
# Usage:
#     scripts/nas/restart.sh

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAS_CMD="$DIR/nas-cmd.sh"
# shellcheck disable=SC1090
source "$DIR/credentials.local" 2>/dev/null || true
NAS_REPO_PATH="${NAS_REPO_PATH:-/volume1/docker/tradingagents}"

SERVICES="${SERVICES:-api web}"   # override with SERVICES="api" or SERVICES="web"
"$NAS_CMD" "cd '$NAS_REPO_PATH' && docker compose restart $SERVICES && docker compose logs --tail=20 $SERVICES"
