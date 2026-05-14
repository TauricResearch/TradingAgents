#!/bin/bash

# Configuration
REGISTRY="${TRADINGAGENTS_REGISTRY:-ghcr.io/madhuboyin}"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
IMAGE_TAG="${TRADINGAGENTS_TAG:-ui-$TIMESTAMP}"

echo "🚀 Starting Targeted Build for TradingAgents Dashboard (ARM64)..."
echo "🏷️  Tagging images as: $IMAGE_TAG"

# Ensure buildx is ready
docker buildx create --use --name pi-builder || true

# Build only the Dashboard UI image
echo "🖥️ Building TradingAgents Dashboard image..."
docker buildx build --platform linux/arm64 \
  -f ui/Dockerfile \
  -t "${REGISTRY}/tradingagents-dashboard:${IMAGE_TAG}" \
  -t "${REGISTRY}/tradingagents-dashboard:latest-arm64" \
  --push .

# Deploy only the dashboard to Kubernetes
echo "☸️ Deploying Dashboard to cluster with tag $IMAGE_TAG..."
sed "s/:latest-arm64/:$IMAGE_TAG/g" k8s/dashboard.yaml | kubectl apply -f -

echo "✅ UI Deployment complete!"
