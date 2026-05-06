#!/usr/bin/env bash
# Tail logs from a service on the NAS.
#
# Usage:
#     scripts/nas/logs.sh                    # default service, last 100 lines, follow
#     scripts/nas/logs.sh --tail=500         # last 500 lines, no follow
#     SERVICE=worker scripts/nas/logs.sh     # different service

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DIR/_lib.sh"

SERVICE="${SERVICE:-$DEFAULT_LOG_SERVICE}"
ARGS="${*:---tail=100 --follow}"
"$NAS_CMD" "cd '$NAS_REPO_PATH' && docker compose logs $ARGS $SERVICE"
