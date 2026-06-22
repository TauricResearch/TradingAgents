#!/usr/bin/env bash
# Build the engine backend image and save it as a tarball that ships INSIDE the
# macOS app. On first launch the app `docker load`s it — so the user pulls
# nothing and configures nothing (Docker Desktop is the only prerequisite).
#
# Dev: the tar lands in macos/TradingDesk/.build (gitignored). The Xcode app
# target's build phase copies it into TradingDesk.app/Contents/Resources, where
# DockerBackendController.bundledImageTar() finds it. To test the load path in
# dev without an Xcode bundle, point the app at the tar:
#   DESK_IMAGE_TAR=<abs path to engine-image.tar.gz> open .build/TradingDesk.app
set -euo pipefail

cd "$(dirname "$0")/.."          # repo root
TAG="${1:-tradingdesk-engine:dev}"
OUT="${2:-macos/TradingDesk/.build/engine-image.tar.gz}"

echo "Building $TAG …"
docker compose build desk-server

mkdir -p "$(dirname "$OUT")"
echo "Saving $TAG -> $OUT …"
docker save "$TAG" | gzip > "$OUT"
echo "Done: $OUT ($(du -h "$OUT" | cut -f1))"
