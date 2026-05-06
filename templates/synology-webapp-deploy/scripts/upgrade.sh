#!/usr/bin/env bash
# Pull the latest, rebuild, and restart $DEPLOY_SERVICES on the NAS.
# Persistent data is in the bind-mounted ./data directory and is never
# touched by this script.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DIR/_lib.sh"

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
echo '[upgrade] rebuilding $DEPLOY_SERVICES…'
docker compose build $DEPLOY_SERVICES
echo '[upgrade] restarting $DEPLOY_SERVICES…'
docker compose up -d $DEPLOY_SERVICES
echo
for s in $DEPLOY_SERVICES; do
    echo \"[upgrade] last 20 log lines (\$s):\"
    docker compose logs --tail=20 \"\$s\" || true
    echo
done
"

echo
echo "[upgrade] done."
