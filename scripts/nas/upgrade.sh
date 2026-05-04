#!/usr/bin/env bash
# Pull latest from the fork, rebuild the gui image, restart the service.
# Safe to run repeatedly. Persistent data is in the bind-mounted ./data
# directory and is never touched by this script.
#
# Usage (from local machine, after credentials.local exists):
#     scripts/nas/upgrade.sh

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED_FILE="$DIR/credentials.local"
NAS_CMD="$DIR/nas-cmd.sh"

[[ -f "$CRED_FILE" ]] || { echo "Missing $CRED_FILE — see credentials.local.example"; exit 2; }
# shellcheck disable=SC1090
source "$CRED_FILE"

NAS_REPO_PATH="${NAS_REPO_PATH:-/volume1/docker/tradingagents}"
NAS_GIT_BRANCH="${NAS_GIT_BRANCH:-main}"
NAS_GIT_REMOTE="${NAS_GIT_REMOTE:-origin}"

echo "[upgrade] pulling $NAS_GIT_REMOTE/$NAS_GIT_BRANCH on the NAS"
"$NAS_CMD" "set -e
cd '$NAS_REPO_PATH'
PRE=\$(git rev-parse --short HEAD)
git fetch '$NAS_GIT_REMOTE' --prune
git checkout '$NAS_GIT_BRANCH'
git pull --ff-only '$NAS_GIT_REMOTE' '$NAS_GIT_BRANCH'
POST=\$(git rev-parse --short HEAD)
if [ \"\$PRE\" = \"\$POST\" ]; then
    echo '[upgrade] no new commits — nothing to do.'
    exit 0
fi
echo \"[upgrade] \$PRE -> \$POST\"
git --no-pager log --oneline \$PRE..\$POST
echo
echo '[upgrade] rebuilding gui image…'
docker compose build gui
echo '[upgrade] restarting gui service…'
docker compose up -d gui
echo
echo '[upgrade] last 30 log lines:'
docker compose logs --tail=30 gui
"

echo
echo "[upgrade] done."
