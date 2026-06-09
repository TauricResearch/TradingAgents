#!/usr/bin/env bash
# Build the MkDocs reports site locally and publish it to the gh-pages branch.
#
# Report Markdown under docs/ is gitignored and never reaches the remote, so CI
# cannot build the site. Instead we build from the local working tree and push
# the compiled HTML to gh-pages, which GitHub Pages serves (Settings -> Pages ->
# Source = "Deploy from a branch", branch = gh-pages / root).
#
# Usage: bash scripts/publish_site.sh

set -euo pipefail

cd "$(dirname "$0")/.."

if [ -x .venv/bin/mkdocs ]; then
  PY=.venv/bin/python
  MK=.venv/bin/mkdocs
else
  PY=python
  MK=mkdocs
fi

echo "==> Reassembling complete reports from stage files"
"$PY" scripts/reassemble_complete_reports.py

echo "==> Building docs/index.md and ticker hubs"
"$PY" scripts/build_reports_site.py

echo "==> Building site and force-pushing to gh-pages"
"$MK" gh-deploy --force

echo "==> Done. GitHub Pages will serve the updated gh-pages branch shortly."
