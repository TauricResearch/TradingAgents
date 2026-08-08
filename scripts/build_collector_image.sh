#!/usr/bin/env bash
# Build the production collector image with authenticated build identity.

set -euo pipefail

if (( $# != 1 )); then
  echo "usage: scripts/build_collector_image.sh IMAGE_TAG" >&2
  exit 64
fi

tag=$1
revision=${GIT_REVISION:-}
nonce=${COLLECTOR_DEPLOYMENT_NONCE:-}
docker_bin=${DOCKER_BIN:-docker}

if ! [[ $revision =~ ^[0-9a-f]{40}$ ]]; then
  echo "GIT_REVISION must be a full lowercase Git SHA" >&2
  exit 64
fi
if [[ -z $nonce ]]; then
  nonce=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
fi
if ! [[ $nonce =~ ^[0-9a-f]{32}$ ]]; then
  echo "COLLECTOR_DEPLOYMENT_NONCE must be 32 lowercase hexadecimal characters" >&2
  exit 64
fi
if [[ -n ${GITHUB_ENV:-} ]]; then
  printf 'COLLECTOR_DEPLOYMENT_NONCE=%s\n' "$nonce" >> "$GITHUB_ENV"
fi

"$docker_bin" build \
  --build-arg "GIT_REVISION=${revision}" \
  --build-arg "COLLECTOR_DEPLOYMENT_NONCE=${nonce}" \
  --file Dockerfile.poller \
  --tag "$tag" .
