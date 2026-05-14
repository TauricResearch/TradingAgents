#!/bin/bash

# Configuration
REGISTRY="your-registry"
IMAGE_TAG="latest-arm64"

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
