# Migration Guide: AI Provider Agnostic Update

## Overview

This project has been updated to support multiple AI/LLM providers instead of being locked to OpenAI. You can now use OpenAI, Ollama (local), Anthropic, Google, Groq, and others.

## What Changed

### 1. New LLM Factory Module

**File:** `tradingagents/llm_factory.py`

A new factory pattern implementation that creates LLM instances for any supported provider. This module:
- Provides a unified interface for all providers
- Handles provider-specific initialization
- Includes helpful error messages for missing dependencies
- Supports: OpenAI, Ollama, Anthropic, Google, Azure, Groq, Together AI, HuggingFace, OpenRouter

### 2. Updated Configuration

**File:** `tradingagents/default_config.py`

Enhanced configuration with:
- `llm_provider`: Specify which provider to use
- `temperature`: Control model randomness
- `llm_kwargs`: Pass additional provider-specific parameters
- Example configurations for all providers (commented)

### 3. Refactored Graph Initialization

**File:** `tradingagents/graph/trading_graph.py`

- Removed hardcoded provider checks (OpenAI, Anthropic, Google)
- Now uses the LLM factory for provider-agnostic initialization
- Simplified code with automatic provider handling

### 4. Type Annotation Updates

**Files:**
- `tradingagents/graph/setup.py`
- `tradingagents/graph/signal_processing.py`
- `tradingagents/graph/reflection.py`

- Removed specific type hints (e.g., `ChatOpenAI`)
- Now accept any LangChain-compatible LLM
- Maintains full functionality while being provider-agnostic

### 5. Updated Dependencies

**File:** `requirements.txt`

- Organized dependencies by purpose
- Added comments for optional provider packages
- Included langchain-core and langchain-community
- Documented which packages are needed for each provider

### 6. Environment Variables

**File:** `.env.example`

- Added examples for all supported providers
- Documented which API keys are needed for each
- Included Ollama configuration (no API key needed)

## New Files

### Documentation

1. **`docs/LLM_PROVIDER_GUIDE.md`**
   - Comprehensive guide for all supported providers
   - Setup instructions for each provider
   - Model recommendations
   - Troubleshooting tips
   - Environment variable setup

2. **`docs/MULTI_PROVIDER_SUPPORT.md`**
   - Quick reference for switching providers
   - Code examples for each provider
   - Installation notes
   - Environment setup

### Examples

3. **`examples/llm_provider_configs.py`**
   - Pre-configured settings for all providers
   - Ready-to-use configuration dictionaries
   - Usage examples

## Migration Steps

### For Existing Users (Currently Using OpenAI)

**No changes required!** The default configuration still uses OpenAI. Your existing code will work as-is.

### To Switch to a Different Provider

#### Option 1: Using Ollama (Free, Local)

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "llama3:70b"
config["quick_think_llm"] = "llama3:8b"
config["backend_url"] = "http://localhost:11434"

ta = TradingAgentsGraph(config=config)
```

**Setup:**
1. Install Ollama: https://ollama.ai
2. Pull models: `ollama pull llama3`
3. Install langchain-community: `pip install langchain-community`

#### Option 2: Using Anthropic Claude

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-3-opus-20240229"
config["quick_think_llm"] = "claude-3-haiku-20240307"

ta = TradingAgentsGraph(config=config)
```

**Setup:**
1. Get API key from https://console.anthropic.com/
2. Set environment: `export ANTHROPIC_API_KEY=your-key`
3. Install: `pip install langchain-anthropic`

#### Option 3: Using Google Gemini

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"
config["deep_think_llm"] = "gemini-1.5-pro"
config["quick_think_llm"] = "gemini-1.5-flash"

ta = TradingAgentsGraph(config=config)
```

**Setup:**
1. Get API key from https://makersuite.google.com/app/apikey
2. Set environment: `export GOOGLE_API_KEY=your-key`
3. Install: `pip install langchain-google-genai` (already in requirements.txt)

## Benefits

### 1. **Cost Savings**
- Use free local models with Ollama (Llama 3, Mistral, etc.)
- Choose cheaper providers like Groq for specific tasks
- Mix and match: expensive models for complex tasks, cheap for simple ones

### 2. **Privacy**
- Run models locally with Ollama
- No data sent to external APIs
- Full control over your data

### 3. **Performance**
- Use Groq for ultra-fast inference
- Choose the best model for each task
- Experiment with different providers

### 4. **Flexibility**
- Not locked to a single vendor
- Easy to switch providers
- Test multiple providers simultaneously

### 5. **Future-Proof**
- Easy to add new providers
- Stay up-to-date with latest models
- Adapt to changing AI landscape

## Breaking Changes

**None!** This update is fully backward compatible. Existing code using OpenAI will continue to work without modifications.

## Testing

To test different providers:

```python
from tradingagents.llm_factory import LLMFactory

# Test provider creation
openai_llm = LLMFactory.create_llm(
    provider="openai",
    model="gpt-4o-mini",
    temperature=0.7
)

ollama_llm = LLMFactory.create_llm(
    provider="ollama",
    model="llama3",
    base_url="http://localhost:11434",
    temperature=0.7
)

# Verify it works
response = openai_llm.invoke("Hello, how are you?")
print(response.content)
```

## Troubleshooting

### Import Errors

If you get `ImportError` for a provider:

```bash
# For Ollama
pip install langchain-community

# For Groq
pip install langchain-groq

# For Together AI
pip install langchain-together
```

### API Key Not Found

Make sure environment variables are set:

```bash
# Check
echo $OPENAI_API_KEY

# Set
export OPENAI_API_KEY=your-key

# Or add to .env file
echo "OPENAI_API_KEY=your-key" >> .env
```

### Ollama Connection Failed

1. Make sure Ollama is running: `ollama serve`
2. Check if model is available: `ollama list`
3. Pull model if needed: `ollama pull llama3`
4. Verify endpoint: default is `http://localhost:11434`

## Support

For detailed provider setup and configuration:
- See `docs/LLM_PROVIDER_GUIDE.md`
- See `docs/MULTI_PROVIDER_SUPPORT.md`
- Check example configs in `examples/llm_provider_configs.py`

## Future Enhancements

Potential future additions:
- Support for more providers (Cohere, AI21, etc.)
- Automatic provider fallback
- Cost tracking per provider
- Performance benchmarking
- Provider-specific optimizations
