#!/usr/bin/env bash
# Quick status of the NAS deployment: container state, health, port, image,
# version (git short SHA), and disk usage of the data dir.
#
# Usage:
#     scripts/nas/status.sh

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAS_CMD="$DIR/nas-cmd.sh"
# shellcheck disable=SC1090
source "$DIR/credentials.local" 2>/dev/null || true

NAS_REPO_PATH="${NAS_REPO_PATH:-/volume1/docker/tradingagents}"
NAS_DATA_PATH="${NAS_DATA_PATH:-$NAS_REPO_PATH/data}"

"$NAS_CMD" "set -e
cd '$NAS_REPO_PATH' 2>/dev/null || { echo 'Repo not found at $NAS_REPO_PATH'; exit 1; }

echo '== git =='
git --no-pager log -1 --oneline
echo
echo '== compose ps =='
docker compose ps
echo
echo '== container health =='
docker inspect --format='State: {{.State.Status}} / Health: {{.State.Health.Status}} / Started: {{.State.StartedAt}}' tradingagents-gui 2>/dev/null || echo '(container not found)'
echo
echo '== image =='
docker image ls --format 'table {{.Repository}}\t{{.Tag}}\t{{.CreatedSince}}\t{{.Size}}' | head -3
echo
echo '== data dir =='
ls -lah '$NAS_DATA_PATH' | head -10
echo
echo '== disk =='
du -sh '$NAS_DATA_PATH' 2>/dev/null || true
"
