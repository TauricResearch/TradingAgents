#!/bin/bash

# Configuration
REGISTRY="${TRADINGAGENTS_REGISTRY:-ghcr.io/madhuboyin}"
# Use a timestamp for the tag to force Kubernetes to pull the new version
TIMESTAMP=$(date +%Y%m%d%H%M%S)
IMAGE_TAG="${TRADINGAGENTS_TAG:-build-$TIMESTAMP}"

echo "🚀 Starting Multi-Arch Build for Raspberry Pi (ARM64)..."
echo "🏷️  Tagging images as: $IMAGE_TAG"

# Ensure buildx is ready
docker buildx create --use --name pi-builder || true

# 1. Build the main TradingAgents CLI image
echo "📦 Building TradingAgents CLI image..."
docker buildx build --platform linux/arm64 \
  -t "${REGISTRY}/tradingagents:${IMAGE_TAG}" \
  -t "${REGISTRY}/tradingagents:latest-arm64" \
  --push .

# 2. Build the Dashboard UI image
echo "🖥️ Building TradingAgents Dashboard image..."
docker buildx build --platform linux/arm64 \
  -f ui/Dockerfile \
  -t "${REGISTRY}/tradingagents-dashboard:${IMAGE_TAG}" \
  -t "${REGISTRY}/tradingagents-dashboard:latest-arm64" \
  --push .

# 3. Deploy to Kubernetes with the specific tag
echo "☸️ Deploying to Raspberry Pi cluster with tag $IMAGE_TAG..."
# Use sed to replace the image tag in the YAML before applying
sed "s/:latest-arm64/:$IMAGE_TAG/g" k8s/workloads.yaml | kubectl apply -f -

echo "✅ Deployment complete!"
