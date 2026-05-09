#!/usr/bin/env bash
# Downloads gitleaks into an isolated local dir (not on PATH) and scans the repo.
# Usage: bash scripts/secrets_scan_local.sh [extra gitleaks flags]
set -euo pipefail

GITLEAKS_VERSION="8.27.2"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${ROOT}/.venv/gitleaks-bin"
GITLEAKS="${BIN_DIR}/gitleaks"

if [[ ! -x "${GITLEAKS}" ]]; then
  echo "Installing gitleaks ${GITLEAKS_VERSION} to ${BIN_DIR}..."
  mkdir -p "${BIN_DIR}"
  OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
  ARCH="$(uname -m)"
  case "${ARCH}" in
    x86_64)        ARCH_TAG="x64"   ;;
    aarch64|arm64) ARCH_TAG="arm64" ;;
    *)             echo "Unsupported architecture: ${ARCH}"; exit 1 ;;
  esac
  URL="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_${OS}_${ARCH_TAG}.tar.gz"
  curl -sSfL "${URL}" | tar -xz -C "${BIN_DIR}" gitleaks
  chmod +x "${GITLEAKS}"
fi

echo "Running gitleaks secrets scan (full history)..."
"${GITLEAKS}" detect --source "${ROOT}" --log-level warn "$@"
