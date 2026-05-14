#!/bin/bash

# Configuration
REGISTRY="${TRADINGAGENTS_REGISTRY:-ghcr.io/madhuboyin}"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
IMAGE_TAG="${TRADINGAGENTS_TAG:-agents-$TIMESTAMP}"

echo "🚀 Starting Targeted Build for TradingAgents Core (ARM64)..."
echo "🏷️  Tagging images as: $IMAGE_TAG"

# Ensure buildx is ready
docker buildx create --use --name pi-builder || true

# Build only the main TradingAgents CLI image
echo "📦 Building TradingAgents CLI image..."
docker buildx build --platform linux/arm64 \
  -t "${REGISTRY}/tradingagents:${IMAGE_TAG}" \
  -t "${REGISTRY}/tradingagents:latest-arm64" \
  --push .

# Deploy only the agents (CronJobs) to Kubernetes
echo "☸️ Deploying Agents to cluster with tag $IMAGE_TAG..."
sed "s/:latest-arm64/:$IMAGE_TAG/g" k8s/agents.yaml | kubectl apply -f -

echo "✅ Agents Deployment complete!"
