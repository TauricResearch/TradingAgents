#!/usr/bin/env bash
# Build the MkDocs reports site locally and optionally publish it to gh-pages.
#
# Report Markdown under docs/ is gitignored and never reaches the remote, so CI
# cannot build the site. Instead we build from the local working tree and push
# the compiled HTML to gh-pages, which GitHub Pages serves (Settings -> Pages ->
# Source = "Deploy from a branch", branch = gh-pages / root).
#
# This script is intentionally model-free: it only reassembles existing report
# stage files, validates generated links, builds MkDocs HTML, and optionally
# publishes the compiled site. Missing extracted summary fields are left as-is.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: bash scripts/publish_site.sh [options]

Options:
  --analysis-date YYYYMMDD|YYYY-MM-DD
      Refresh and validate the summary for a specific analysis date.
      Defaults to the latest date discovered under docs/.
  --build-only
      Build and validate _site locally, but do not push gh-pages.
  --dry-run
      Run the report workflow against a temporary docs copy. Does not write
      _site or push gh-pages.
  -h, --help
      Show this help.

No LLM/model calls are made by this script.
EOF
}

analysis_date=""
build_only=0
dry_run=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --analysis-date)
      if [ "$#" -lt 2 ]; then
        echo "error: --analysis-date requires a value" >&2
        exit 2
      fi
      analysis_date="$2"
      shift 2
      ;;
    --build-only)
      build_only=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
else
  PY=python
fi

if [ -x .venv/bin/mkdocs ]; then
  MK=.venv/bin/mkdocs
else
  MK=mkdocs
fi

workflow_args=(--allow-incomplete --allow-summary-na)
if [ -n "$analysis_date" ]; then
  workflow_args+=(--analysis-date "$analysis_date")
fi
if [ "$dry_run" -eq 1 ]; then
  workflow_args+=(--dry-run)
fi

echo "==> Refreshing and validating report docs without model calls"
"$PY" scripts/report_workflow.py "${workflow_args[@]}"

if [ "$dry_run" -eq 1 ]; then
  echo "==> Dry run complete; _site was not rebuilt and gh-pages was not pushed."
  exit 0
fi

if [ "$build_only" -eq 1 ]; then
  echo "==> Build complete; gh-pages was not pushed."
  exit 0
fi

echo "==> Publishing compiled site to gh-pages"
"$MK" gh-deploy --force

echo "==> Done. GitHub Pages will serve the updated gh-pages branch shortly."
