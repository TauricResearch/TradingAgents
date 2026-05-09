#!/usr/bin/env bash
# Mirror of .github/workflows/osv-scan.yml for local runs.
# Downloads the osv-scanner binary into a local cache dir (no PATH pollution).
set -euo pipefail

OSV_VERSION="2.2.3"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${ROOT}/.venv/osv-scanner-bin"
OSV="${BIN_DIR}/osv-scanner"

if [[ ! -x "${OSV}" ]]; then
  echo "Installing osv-scanner ${OSV_VERSION} to ${BIN_DIR}..."
  mkdir -p "${BIN_DIR}"
  OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
  ARCH="$(uname -m)"
  case "${ARCH}" in
    x86_64)        ARCH_TAG="amd64" ;;
    aarch64|arm64) ARCH_TAG="arm64" ;;
    *)             echo "Unsupported architecture: ${ARCH}"; exit 1 ;;
  esac
  URL="https://github.com/google/osv-scanner/releases/download/v${OSV_VERSION}/osv-scanner_${OS}_${ARCH_TAG}"
  curl -sSfL "${URL}" -o "${OSV}"
  chmod +x "${OSV}"
fi

"${OSV}" scan source --recursive --skip-git "${ROOT}" "$@"
