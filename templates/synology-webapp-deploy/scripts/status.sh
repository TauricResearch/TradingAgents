#!/usr/bin/env bash
# Quick status: container state + health + image + git SHA + data dir size.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DIR/_lib.sh"

"$NAS_CMD" "set -e
cd '$NAS_REPO_PATH' 2>/dev/null || { echo 'Repo not found at $NAS_REPO_PATH'; exit 1; }

echo '== git =='
git --no-pager log -1 --oneline
echo
echo '== compose ps =='
docker compose ps
echo
echo '== container health =='
for c in $PRIMARY_CONTAINERS; do
    docker inspect --format='{{.Name}}: {{.State.Status}} / Health: {{.State.Health.Status}} / Started: {{.State.StartedAt}}' \"\$c\" 2>/dev/null || echo \"\$c: (not running)\"
done
echo
echo '== data dir =='
ls -lah '$NAS_DATA_PATH' 2>/dev/null | head -10 || echo '(no data dir)'
echo
echo '== disk =='
du -sh '$NAS_DATA_PATH' 2>/dev/null || true
"
