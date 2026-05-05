#!/usr/bin/env bash
# Tail GUI service logs from the NAS.
#
# Usage:
#     scripts/nas/logs.sh             # last 100 lines, then follow
#     scripts/nas/logs.sh --tail=500  # last 500 lines, no follow

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAS_CMD="$DIR/nas-cmd.sh"
# shellcheck disable=SC1090
source "$DIR/credentials.local" 2>/dev/null || true
NAS_REPO_PATH="${NAS_REPO_PATH:-/volume1/docker/tradingagents}"

ARGS="${*:---tail=100 --follow}"
SERVICE="${SERVICE:-api}"   # override with SERVICE=web ./logs.sh
"$NAS_CMD" "cd '$NAS_REPO_PATH' && docker compose logs $ARGS $SERVICE"
