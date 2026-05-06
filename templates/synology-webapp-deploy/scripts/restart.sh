#!/usr/bin/env bash
# Restart services without rebuilding (fast — for picking up an .env
# change or kicking a stuck process). Use upgrade.sh for code changes.
#
# Usage:
#     scripts/nas/restart.sh                       # all DEPLOY_SERVICES
#     SERVICES="api" scripts/nas/restart.sh        # just one

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DIR/_lib.sh"

SERVICES="${SERVICES:-$DEPLOY_SERVICES}"
"$NAS_CMD" "cd '$NAS_REPO_PATH' && docker compose restart $SERVICES && docker compose logs --tail=20 $SERVICES"
