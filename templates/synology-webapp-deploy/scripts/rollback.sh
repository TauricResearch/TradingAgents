#!/usr/bin/env bash
# Roll the NAS clone back to a previous commit and rebuild.
#
# Usage:
#     scripts/nas/rollback.sh <short-sha>
#     scripts/nas/rollback.sh previous          # i.e. HEAD~1

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DIR/_lib.sh"

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
docker compose build $DEPLOY_SERVICES
docker compose up -d $DEPLOY_SERVICES
docker compose logs --tail=20 $DEPLOY_SERVICES
"
