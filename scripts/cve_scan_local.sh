#!/usr/bin/env bash
# Isolated venv so pip-audit only sees TradingAgents deps (matches CI), not your global/site packages.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/.venv/cve-scan"
if [[ ! -x "${VENV}/bin/python" ]]; then
  python3 -m venv "${VENV}"
fi
"${VENV}/bin/python" -m pip install --upgrade pip -q
"${VENV}/bin/pip" install -q pip-audit
"${VENV}/bin/pip" install -q -e "${ROOT}"
# Another venv may be active in the shell (e.g. ./venv); pip-audit warns if VIRTUAL_ENV
# disagrees with the interpreter we audit. We always audit this script's isolated venv.
env -u VIRTUAL_ENV "${VENV}/bin/pip-audit" --desc --skip-editable "$@"
