# Embedding Configuration Guide

## Overview

This guide explains the new separated embedding configuration feature in TradingAgents. The system now allows you to use different providers for chat models and embeddings, enabling more flexible deployment scenarios.

## Key Features

1. **Separate Embedding Client**: Chat models and embedding models use independent configurations
2. **Multiple Embedding Providers**: Support for OpenAI, Ollama (local), or disabled memory
3. **Graceful Fallback**: System continues to operate even when embeddings are unavailable
4. **Provider Independence**: Use OpenRouter/Anthropic for chat while using OpenAI for embeddings

## Why This Matters

Previously, the memory system used the same backend URL as the chat model, causing issues when:
- Using OpenRouter (which doesn't support OpenAI embedding endpoints)
- Using Anthropic or Google for chat (which don't provide embeddings)
- Running in environments without embedding access

Now you can:
- Use OpenRouter/Anthropic/Google for chat models
- Use OpenAI for embeddings (recommended)
- Use Ollama for local embeddings
- Disable memory entirely if needed

## Configuration Options

### Via CLI (Interactive)

When running the CLI, you'll see a new Step 7 for embedding configuration:

```bash
python -m cli.main
```

You'll be prompted to select:
1. **OpenAI (recommended)** - Uses OpenAI's embedding API
2. **Ollama (local)** - Uses local Ollama embedding models
3. **Disable Memory** - Runs without memory/context retrieval

### Via Code (Direct Configuration)

Update your configuration dictionary:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = {
    # Chat LLM settings (can be any provider)
    "llm_provider": "openrouter",
    "backend_url": "https://openrouter.ai/api/v1",
    "deep_think_llm": "deepseek/deepseek-chat-v3-0324:free",
    "quick_think_llm": "meta-llama/llama-3.3-8b-instruct:free",
    
    # Embedding settings (separate from chat)
    "embedding_provider": "openai",
    "embedding_backend_url": "https://api.openai.com/v1",
    "embedding_model": "text-embedding-3-small",
    "enable_memory": True,
    
    # Other settings...
}

graph = TradingAgentsGraph(selected_analysts=["market", "news"], config=config)
```

## Configuration Parameters

### `embedding_provider`
- **Type**: `string`
- **Options**: `"openai"`, `"ollama"`, `"none"`
- **Default**: `"openai"`
- **Description**: The embedding service provider

### `embedding_backend_url`
- **Type**: `string`
- **Default**: `"https://api.openai.com/v1"` (for OpenAI)
- **Description**: API endpoint URL for embeddings

### `embedding_model`
- **Type**: `string`
- **Default**: `"text-embedding-3-small"` (for OpenAI)
- **Description**: The embedding model to use

### `enable_memory`
- **Type**: `boolean`
- **Default**: `True`
- **Description**: Enable/disable the memory system

## Common Scenarios

### Scenario 1: OpenRouter for Chat + OpenAI for Embeddings

**Best for**: Cost-effective chat with reliable embeddings

```python
config = {
    "llm_provider": "openrouter",
    "backend_url": "https://openrouter.ai/api/v1",
    "deep_think_llm": "deepseek/deepseek-chat-v3-0324:free",
    "quick_think_llm": "meta-llama/llama-3.3-8b-instruct:free",
    
    "embedding_provider": "openai",
    "embedding_backend_url": "https://api.openai.com/v1",
    "embedding_model": "text-embedding-3-small",
    "enable_memory": True,
}
```

**Required API Keys**:
- `OPENROUTER_API_KEY` (for chat)
- `OPENAI_API_KEY` (for embeddings)

### Scenario 2: All Local with Ollama

**Best for**: Complete offline/local deployment

```python
config = {
    "llm_provider": "ollama",
    "backend_url": "http://localhost:11434/v1",
    "deep_think_llm": "llama3.1",
    "quick_think_llm": "llama3.2",
    
    "embedding_provider": "ollama",
    "embedding_backend_url": "http://localhost:11434/v1",
    "embedding_model": "nomic-embed-text",
    "enable_memory": True,
}
```

**Prerequisites**:
- Ollama installed and running
- Models pulled: `ollama pull llama3.1 llama3.2 nomic-embed-text`

### Scenario 3: Anthropic for Chat, No Memory

**Best for**: Using providers without embedding support

```python
config = {
    "llm_provider": "anthropic",
    "backend_url": "https://api.anthropic.com/",
    "deep_think_llm": "claude-sonnet-4-0",
    "quick_think_llm": "claude-3-5-haiku-latest",
    
    "embedding_provider": "none",
    "enable_memory": False,
}
```

**Note**: Memory and context retrieval will be disabled.

### Scenario 4: OpenAI for Everything (Default)

**Best for**: Simplicity and full feature support

```python
config = {
    "llm_provider": "openai",
    "backend_url": "https://api.openai.com/v1",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    
    # Embeddings will auto-configure to use OpenAI
}
```

## Environment Variables

Set the appropriate API keys based on your configuration:

```bash
# For OpenAI (chat or embeddings)
export OPENAI_API_KEY="sk-..."

# For OpenRouter (chat)
export OPENROUTER_API_KEY="sk-or-..."

# For Anthropic (chat)
export ANTHROPIC_API_KEY="sk-ant-..."

# For Google (chat)
export GOOGLE_API_KEY="..."
```

## Graceful Degradation

The memory system gracefully handles failures:

1. **Embedding API Unavailable**: Returns empty memories, logs warning, continues execution
2. **Invalid Configuration**: Disables memory, logs error, continues execution
3. **Network Errors**: Skips memory operations, logs error, continues execution

Example log output when embeddings fail:

```
WARNING: Failed to initialize embedding client: Connection error. Memory will be disabled.
INFO: Memory disabled for bull_memory
INFO: Memory disabled for bear_memory
...
```

The agents continue to function without memory-based context.

## Checking Memory Status

You can check if memory is enabled:

```python
# After initializing the graph
print(f"Bull memory enabled: {graph.bull_memory.is_enabled()}")
print(f"Bear memory enabled: {graph.bear_memory.is_enabled()}")
```

## Migration Guide

### From Previous Version

If you have existing code using the old configuration:

**Old (single backend for everything):**
```python
config = {
    "llm_provider": "openai",
    "backend_url": "https://api.openai.com/v1",
}
```

**New (explicit embedding config):**
```python
config = {
    "llm_provider": "openai",
    "backend_url": "https://api.openai.com/v1",
    # Add these for explicit control:
    "embedding_provider": "openai",
    "embedding_backend_url": "https://api.openai.com/v1",
    "embedding_model": "text-embedding-3-small",
}
```

**Note**: The old configuration still works! The system auto-configures embeddings based on smart defaults.

## Smart Defaults

If you don't specify embedding configuration, the system applies these rules:

1. **embedding_provider**: Defaults to `"openai"`
2. **embedding_backend_url**: 
   - `"openai"` → `"https://api.openai.com/v1"`
   - `"ollama"` → `"http://localhost:11434/v1"`
3. **embedding_model**:
   - `"openai"` → `"text-embedding-3-small"`
   - `"ollama"` → `"nomic-embed-text"`
4. **enable_memory**: Defaults to `True`

## Troubleshooting

### Issue: "Failed to get embedding: 401 Unauthorized"

**Cause**: Missing or invalid API key for embedding provider

**Solution**: 
```bash
export OPENAI_API_KEY="your-actual-key"
```

### Issue: "Memory disabled for all agents"

**Cause**: Embedding provider set to `"none"` or initialization failed

**Solution**: Check your `embedding_provider` setting and API keys

### Issue: OpenRouter returns HTML instead of embeddings

**Cause**: Trying to use OpenRouter backend for embeddings (not supported)

**Solution**: Set separate embedding provider:
```python
config["embedding_provider"] = "openai"
config["embedding_backend_url"] = "https://api.openai.com/v1"
```

### Issue: "ChromaDB collection creation failed"

**Cause**: ChromaDB initialization error

**Solution**: 
- Ensure ChromaDB is installed: `pip install chromadb`
- Check disk space and permissions
- Set `enable_memory: False` to bypass

## Performance Considerations

### Embedding Costs

| Provider | Model | Cost per 1M tokens | Speed |
|----------|-------|-------------------|-------|
| OpenAI | text-embedding-3-small | ~$0.02 | Fast |
| OpenAI | text-embedding-3-large | ~$0.13 | Fast |
| Ollama | nomic-embed-text | Free | Medium (local) |

### Memory Impact

- **With Memory**: Agents use historical context, better decisions
- **Without Memory**: Faster initialization, no embedding costs, stateless

## Best Practices

1. **Production**: Use OpenAI embeddings for reliability
2. **Development**: Use Ollama for cost-free testing
3. **CI/CD**: Disable memory (`enable_memory: False`) for faster tests
4. **Multi-provider**: Use different providers for chat and embeddings to optimize cost/performance

## API Reference

### FinancialSituationMemory

```python
class FinancialSituationMemory:
    def __init__(self, name: str, config: Dict[str, Any])
    
    def is_enabled(self) -> bool:
        """Check if memory is enabled and functioning."""
    
    def add_situations(self, situations_and_advice: List[Tuple[str, str]]) -> bool:
        """Add financial situations and recommendations to memory."""
    
    def get_memories(self, current_situation: str, n_matches: int = 1) -> List[Dict]:
        """Retrieve matching memories for the current situation."""
```

### Example Usage

```python
from tradingagents.agents.utils.memory import FinancialSituationMemory

config = {
    "embedding_provider": "openai",
    "embedding_backend_url": "https://api.openai.com/v1",
    "embedding_model": "text-embedding-3-small",
    "enable_memory": True,
}

memory = FinancialSituationMemory("test_memory", config)

if memory.is_enabled():
    # Add memories
    memory.add_situations([
        ("High volatility market", "Reduce position sizes"),
        ("Strong uptrend", "Consider scaling in"),
    ])
    
    # Query memories
    matches = memory.get_memories("Market showing volatility", n_matches=2)
    for match in matches:
        print(f"Score: {match['similarity_score']:.2f}")
        print(f"Recommendation: {match['recommendation']}")
```

## Support

For issues or questions:
1. Check the [main README](../README.md)
2. Review error logs for specific failure messages
3. Open an issue on GitHub with configuration details

## Changelog

### Version 2.0 (Current)
- ✅ Separated embedding configuration from chat LLM
- ✅ Support for multiple embedding providers
- ✅ Graceful fallback when embeddings unavailable
- ✅ CLI step for embedding provider selection
- ✅ Smart defaults for backward compatibility

### Version 1.0 (Legacy)
- Single backend URL for all operations
- Embedding failures caused system crashes
- No provider flexibility