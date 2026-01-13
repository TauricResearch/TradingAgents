#!/bin/bash

# Stop and remove existing container if it exists
docker rm -f embedding-service 2>/dev/null || true

echo "🚀 Starting Local Embedding Service (Hugging Face TEI)..."
echo "ℹ️  Note: The previous image (clems4ever/all-minilm-l6-v2-go) is a CLI tool, not a server."
echo "    Switching to ghcr.io/huggingface/text-embeddings-inference:cpu-latest which provides a compatible API."

# Run Hugging Face Text Embeddings Inference (compatible with OpenAI client)
docker run -d \
  --name embedding-service \
  --restart unless-stopped \
  -p 11434:80 \
  -v $PWD/data_cache:/data \
  -e MAX_CONCURRENT_REQUESTS=4 \
  ghcr.io/huggingface/text-embeddings-inference:cpu-latest \
  --model-id sentence-transformers/all-MiniLM-L6-v2

echo "✅ Service started!"
echo "   URL: http://localhost:11434/v1"
