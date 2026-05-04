#!/usr/bin/env bash
# Roll the NAS clone back to a previous commit and rebuild. Useful if an
# upgrade goes sideways. Pass either:
#   - a specific short SHA: scripts/nas/rollback.sh abc1234
#   - "previous" to undo the last commit: scripts/nas/rollback.sh previous
#
# Persistent data in ./data is untouched — DB, config, archives all stay.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAS_CMD="$DIR/nas-cmd.sh"
# shellcheck disable=SC1090
source "$DIR/credentials.local" 2>/dev/null || true
NAS_REPO_PATH="${NAS_REPO_PATH:-/volume1/docker/tradingagents}"

TARGET="${1:-}"
[[ -n "$TARGET" ]] || { echo "Usage: $0 <short-sha|previous>"; exit 2; }

if [[ "$TARGET" = "previous" ]]; then
    REF="HEAD~1"
else
    REF="$TARGET"
fi

"$NAS_CMD" "set -e
cd '$NAS_REPO_PATH'
echo \"[rollback] currently at: \$(git rev-parse --short HEAD)\"
echo \"[rollback] resetting to: $REF\"
git checkout '$REF'
docker compose build gui
docker compose up -d gui
docker compose logs --tail=20 gui
"
