#!/usr/bin/env bash
# Run ruff lint and format checks locally, mirroring .github/workflows/lint.yml.
# Usage: bash scripts/lint_local.sh [--fix]
#   --fix   Apply auto-fixes and reformat in place instead of just checking.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if ! command -v ruff >/dev/null 2>&1; then
  echo "ruff is not installed. Install with: pip install ruff  (or: uv tool install ruff)"
  exit 1
fi

if [[ "${1:-}" == "--fix" ]]; then
  ruff check --fix .
  ruff format .
else
  ruff check .
  ruff format --check .
fi
