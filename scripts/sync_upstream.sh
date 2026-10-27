#!/usr/bin/env bash
# Refresh klepsydra/TradingAgents from upstream TauricResearch/TradingAgents (ROBIN-1684).
# Safe defaults: fetch + merge upstream/main into a sync branch, push, open PR.
# Never force-pushes main. Does not overwrite local .env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

UPSTREAM_REMOTE="${UPSTREAM_REMOTE:-upstream}"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/TauricResearch/TradingAgents.git}"
BRANCH="${SYNC_BRANCH:-cursor/upstream-sync-$(date -u +%Y%m%d)-a109}"

git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1 \
  || git remote add "$UPSTREAM_REMOTE" "$UPSTREAM_URL"

echo "Fetching $UPSTREAM_REMOTE…"
git fetch "$UPSTREAM_REMOTE" main

git stash push --keep-index --include-untracked -m "cursor-pre-upstream-sync $(date -u +%Y%m%dT%H%M%SZ)" || true
git checkout main
git pull --ff-only origin main
git checkout -b "$BRANCH"

if git merge --no-edit "$UPSTREAM_REMOTE/main"; then
  echo "Merge clean."
else
  echo "Merge conflicts — resolve manually, then: git push -u origin $BRANCH && gh pr create" >&2
  exit 2
fi

# Smoke: compose config if docker present (optional)
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker compose config >/dev/null && echo "docker compose config ok"
fi

git push -u origin "$BRANCH"
gh pr create --repo klepsydra/TradingAgents --base main --head "$BRANCH" \
  --title "chore: sync upstream TauricResearch/TradingAgents $(date -u +%Y-%m-%d)" \
  --body "Automated upstream sync via scripts/sync_upstream.sh (ROBIN-1684)." \
  || echo "PR may already exist"

echo "Done. Review/merge the PR, then re-run scripts/install_site.sh if needed."
