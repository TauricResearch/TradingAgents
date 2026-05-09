#!/usr/bin/env bash
# Mirror of .github/workflows/container-scan.yml for local runs.
# Uses Docker to run hadolint and trivy without polluting your system.
# Requires: docker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed or not on PATH. This script runs hadolint and"
  echo "trivy in containers to match CI exactly. Install Docker first, or run"
  echo "the binaries directly:"
  echo "  brew install hadolint trivy   # macOS"
  exit 1
fi

echo "==> hadolint Dockerfile (failure-threshold=warning)"
docker run --rm -i \
  -v "${ROOT}/Dockerfile:/Dockerfile:ro" \
  hadolint/hadolint:latest \
  hadolint --failure-threshold warning /Dockerfile

echo
echo "==> trivy filesystem scan (CRITICAL,HIGH; ignore-unfixed)"
docker run --rm \
  -v "${ROOT}:/workspace:ro" \
  aquasec/trivy:latest \
  fs \
    --severity CRITICAL,HIGH \
    --ignore-unfixed \
    --exit-code 1 \
    /workspace
