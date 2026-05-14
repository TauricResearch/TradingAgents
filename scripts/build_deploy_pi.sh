#!/bin/bash

# Configuration
REGISTRY="${TRADINGAGENTS_REGISTRY:-ghcr.io/YOUR_GITHUB_USERNAME}"
IMAGE_TAG="${TRADINGAGENTS_TAG:-latest-arm64}"

if [ "$REGISTRY" == "ghcr.io/YOUR_GITHUB_USERNAME" ]; then
  echo "⚠️  Warning: Using placeholder registry. Set TRADINGAGENTS_REGISTRY to override."
fi

echo "🚀 Starting Multi-Arch Build for Raspberry Pi (ARM64)..."

# Ensure buildx is ready
docker buildx create --use --name pi-builder || true

# 1. Build the main TradingAgents CLI image
echo "📦 Building TradingAgents CLI image..."
docker buildx build --platform linux/arm64 \
  -t "${REGISTRY}/tradingagents:${IMAGE_TAG}" \
  --push .

# 2. Build the Dashboard UI image
echo "🖥️ Building TradingAgents Dashboard image..."
docker buildx build --platform linux/arm64 \
  -f ui/Dockerfile \
  -t "${REGISTRY}/tradingagents-dashboard:${IMAGE_TAG}" \
  --push .

# 3. Deploy to Kubernetes
echo "☸️ Deploying to Raspberry Pi cluster..."
kubectl apply -f k8s/

echo "✅ Deployment complete!"
