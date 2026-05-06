#!/usr/bin/env bash
# Fetch all open PRs as markdown via defuddle.
# Usage: bash scripts/pr-fetch-all.sh [REPO]
# Default repo: pjsvis/TradingAgents

set -euo pipefail

REPO="${1:-pjsvis/TradingAgents}"
OUTDIR="debriefs/reviews"
mkdir -p "$OUTDIR"

echo "Fetching open PRs for $REPO..."

gh pr list --repo "$REPO" \
  --json number,title,updatedAt \
  --state open --limit 20 | \
jq -r '.[] | "\(.number)"' | \
while read -r num; do
  url="https://github.com/$REPO/pull/$num"
  date="$(date +%Y-%m-%d)"
  file="$OUTDIR/pr-${num}-${date}.md"

  # Skip if already fetched today
  if [[ -f "$file" ]]; then
    echo "  PR #$num already cached today — skipping"
    continue
  fi

  echo "  PR #$num → $file"
  defuddle parse --markdown "$url" > "$file" || {
    echo "    ⚠️ defuddle failed for PR #$num"
    rm -f "$file"
  }
done

echo "Done. Reviews saved to $OUTDIR"
