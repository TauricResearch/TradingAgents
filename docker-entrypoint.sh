#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# Start Ollama serve in the background
echo "Starting Ollama service..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready by checking the API endpoint
echo "Waiting for Ollama to be ready..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama is ready!"
        break
    fi
    echo "Waiting for Ollama... (attempt $((attempt + 1))/$max_attempts)"
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -eq $max_attempts ]; then
    echo "Error: Ollama failed to start within the expected time"
    exit 1
fi

# Pull the required model. Use LLM_DEEP_THINK_MODEL, default to qwen:0.5b if not set.
MODEL_TO_PULL=${LLM_DEEP_THINK_MODEL:-"qwen3:0.6b"}
echo "Pulling Ollama model: $MODEL_TO_PULL..."
ollama pull "$MODEL_TO_PULL"
echo "Model $MODEL_TO_PULL pulled."

echo "Pulling embeddings model..."
ollama pull nomic-embed-text
echo "Embeddings model pulled."
# List models to verify the pull
echo "Listing available models..."
ollama list # List models for verification

# Test the connection before running the main application
# TODO: run based on flag for testing
echo "Testing Ollama connection..."
python test_ollama_connection.py
if [ $? -ne 0 ]; then
    echo "Error: Ollama connection test failed"
    exit 1
fi

echo "Ollama setup complete. Executing command: $@"
# Execute the CMD or the command passed to docker run
exec python -m cli.main "$@" 


# Optional: clean up Ollama server on exit (might be complex with exec)
# trap "echo 'Stopping Ollama service...'; kill $OLLAMA_PID; exit 0" SIGINT SIGTERM
