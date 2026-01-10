# Local Embeddings Setup Guide

This guide explains how to set up local embeddings for the TradingAgents framework.

## Why Local Embeddings?

When using LLM providers that don't support embeddings (like Anthropic), or when you want to avoid additional API costs, you need a local embedding solution.

## Recommended: Run in Docker

The recommended approach is to run the embedding service in a Docker container. This keeps your main application environment clean and avoids installing heavy dependencies like PyTorch on your host machine.

### 1. Run the Embedding Service
Use the provided script to start the service:

```bash
./startEmbedding.sh
```

This runs **Hugging Face Text Embeddings Inference (TEI)**, a high-performance server compatible with the OpenAI API.

*(Note: The Go-based image `clems4ever/all-minilm-l6-v2-go` is a CLI tool and cannot merely be run as a server.)*

### 2. Configure TradingAgents

Add (or update) these lines in your `.env` file:

```bash
# Point to your local embedding service (TEI supports /v1 API)
EMBEDDING_API_URL=http://localhost:11434/v1

# The model name configured in the start script
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### 3. Verify Setup

Run the verification script:

```bash
python3 verify_local_embeddings.py
```

## Alternative: Local Installation (Development Only)

If you prefer to run everything locally without Docker (e.g., for development), you can install the library directly.

**⚠️ Warning:** This adds ~500MB of PyTorch dependencies to your environment.

### 1. Install Dependencies

```bash
pip install sentence-transformers
```

### 2. Configure TradingAgents

If you don't set `EMBEDDING_API_URL`, the system will attempt to import `sentence-transformers` automatically when using Anthropic.

```bash
# Optional: Force local provider
EMBEDDING_PROVIDER=local
```

## Supported Providers

| LLM Provider | Default Behavior | Recommended Setup |
|--------------|------------------|-------------------|
| **Anthropic** | Tries local service URL | **Docker Service** |
| **Ollama** | Uses Ollama API | Ensure Ollama is running |
| **OpenAI** | Uses OpenAI API | No setup needed |
| **Google** | Uses Google API | No setup needed |

## FAQ

**Q: Why Docker?**
A: `sentence-transformers` requires PyTorch, which is a very large dependency (~500MB+). Putting it in a container keeps your main application lightweight and portable.

**Q: Can I use GPU?**
A: Yes! Use the GPU version of the container: `ghcr.io/huggingface/text-embeddings-inference:latest` (requires NVIDIA Container Toolkit).

**Q: Can I use Ollama instead?**
A: Yes. Set `EMBEDDING_API_URL=http://localhost:11434/v1` and `EMBEDDING_MODEL=nomic-embed-text` (or your preferred Ollama model).
