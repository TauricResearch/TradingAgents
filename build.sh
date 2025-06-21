#!/bin/bash

# Enable BuildKit for faster builds
export DOCKER_BUILDKIT=1

# Build the image with BuildKit optimizations
echo "Building with BuildKit optimizations..."
docker build \
    --progress=plain \
    --tag tradingagents:latest \
    .

echo "Build completed!"
echo ""
echo "To run the container:"
echo "docker run -it tradingagents2:latest"
echo ""
echo "To test Ollama connection first:"
echo "docker run --rm -it tradingagents:latest python test_ollama_connection.py"
echo ""
echo "To build with additional BuildKit features:"
echo "docker build --build-arg BUILDKIT_INLINE_CACHE=1 --tag tradingagents:latest ." 