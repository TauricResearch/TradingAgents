# LLM Provider Configuration Guide

This project now supports multiple AI/LLM providers through a unified interface. You can easily switch between providers by modifying the configuration.

## Supported Providers

The following providers are currently supported:

1. **OpenAI** - GPT-4, GPT-4o, GPT-3.5-turbo, etc.
2. **Ollama** - Local models (Llama 3, Mistral, etc.)
3. **Anthropic** - Claude models (Opus, Sonnet, Haiku)
4. **Google** - Gemini models
5. **Azure OpenAI** - Microsoft's Azure-hosted OpenAI models
6. **OpenRouter** - Access to multiple models through one API
7. **Groq** - Fast inference for open-source models
8. **Together AI** - Open-source models
9. **HuggingFace** - Models from HuggingFace Hub

## Configuration

### Basic Configuration

Edit `tradingagents/default_config.py` or pass a custom config dictionary:

```python
config = {
    "llm_provider": "openai",  # Provider name
    "deep_think_llm": "gpt-4o",  # Model for complex reasoning
    "quick_think_llm": "gpt-4o-mini",  # Model for quick tasks
    "backend_url": "https://api.openai.com/v1",  # API endpoint (optional)
    "temperature": 0.7,  # Sampling temperature
    "llm_kwargs": {},  # Additional provider-specific parameters
}
```

## Provider-Specific Examples

### OpenAI (Default)

```python
config = {
    "llm_provider": "openai",
    "deep_think_llm": "gpt-4o",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    "temperature": 0.7,
}
```

**Required Environment Variables:**
```bash
export OPENAI_API_KEY=sk-your-api-key-here
```

**Required Packages:**
```bash
pip install langchain-openai
```

---

### Ollama (Local Models)

```python
config = {
    "llm_provider": "ollama",
    "deep_think_llm": "llama3:70b",  # Or llama3, mistral, etc.
    "quick_think_llm": "llama3:8b",
    "backend_url": "http://localhost:11434",  # Default Ollama endpoint
    "temperature": 0.7,
}
```

**Setup:**
1. Install Ollama from https://ollama.ai
2. Pull models: `ollama pull llama3`
3. Verify: `ollama list`

**Required Environment Variables:**
- None (uses local Ollama instance)

**Required Packages:**
```bash
pip install langchain-community
```

---

### Anthropic (Claude)

```python
config = {
    "llm_provider": "anthropic",
    "deep_think_llm": "claude-3-opus-20240229",
    "quick_think_llm": "claude-3-haiku-20240307",
    "temperature": 0.7,
}
```

**Required Environment Variables:**
```bash
export ANTHROPIC_API_KEY=sk-ant-your-api-key-here
```

**Required Packages:**
```bash
pip install langchain-anthropic
```

---

### Google (Gemini)

```python
config = {
    "llm_provider": "google",
    "deep_think_llm": "gemini-1.5-pro",
    "quick_think_llm": "gemini-1.5-flash",
    "temperature": 0.7,
}
```

**Required Environment Variables:**
```bash
export GOOGLE_API_KEY=your-google-api-key-here
```

**Required Packages:**
```bash
pip install langchain-google-genai
```

---

### OpenRouter (Multi-Provider)

```python
config = {
    "llm_provider": "openrouter",
    "deep_think_llm": "anthropic/claude-3-opus",
    "quick_think_llm": "anthropic/claude-3-haiku",
    "backend_url": "https://openrouter.ai/api/v1",
    "temperature": 0.7,
}
```

**Required Environment Variables:**
```bash
export OPENAI_API_KEY=sk-or-your-openrouter-key
```

**Required Packages:**
```bash
pip install langchain-openai
```

---

### Groq (Fast Inference)

```python
config = {
    "llm_provider": "groq",
    "deep_think_llm": "mixtral-8x7b-32768",
    "quick_think_llm": "llama3-8b-8192",
    "temperature": 0.7,
}
```

**Required Environment Variables:**
```bash
export GROQ_API_KEY=gsk-your-groq-api-key
```

**Required Packages:**
```bash
pip install langchain-groq
```

---

### Azure OpenAI

```python
config = {
    "llm_provider": "azure",
    "deep_think_llm": "gpt-4-deployment-name",
    "quick_think_llm": "gpt-35-turbo-deployment-name",
    "backend_url": "https://your-resource.openai.azure.com/",
    "temperature": 0.7,
    "llm_kwargs": {
        "api_version": "2024-02-01",
    }
}
```

**Required Environment Variables:**
```bash
export AZURE_OPENAI_API_KEY=your-azure-key
export AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
```

**Required Packages:**
```bash
pip install langchain-openai
```

---

### Together AI

```python
config = {
    "llm_provider": "together",
    "deep_think_llm": "meta-llama/Llama-3-70b-chat-hf",
    "quick_think_llm": "meta-llama/Llama-3-8b-chat-hf",
    "temperature": 0.7,
}
```

**Required Environment Variables:**
```bash
export TOGETHER_API_KEY=your-together-api-key
```

**Required Packages:**
```bash
pip install langchain-together
```

---

## Usage in Code

### Using Default Configuration

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Uses default config from tradingagents/default_config.py
graph = TradingAgentsGraph()
```

### Using Custom Configuration

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Custom config for Ollama
custom_config = {
    "llm_provider": "ollama",
    "deep_think_llm": "llama3:70b",
    "quick_think_llm": "llama3:8b",
    "backend_url": "http://localhost:11434",
    "temperature": 0.7,
    # ... other config options
}

graph = TradingAgentsGraph(config=custom_config)
```

### Programmatically Creating LLM Instances

```python
from tradingagents.llm_factory import LLMFactory, get_llm_instance

# Method 1: Direct factory usage
llm = LLMFactory.create_llm(
    provider="ollama",
    model="llama3",
    base_url="http://localhost:11434",
    temperature=0.7
)

# Method 2: Using config dictionary
config = {
    "llm_provider": "anthropic",
    "quick_think_llm": "claude-3-haiku-20240307",
    "temperature": 0.7,
}
llm = get_llm_instance(config, model_type="quick_think")
```

## Advanced Configuration

### Additional LLM Parameters

You can pass additional provider-specific parameters via `llm_kwargs`:

```python
config = {
    "llm_provider": "openai",
    "deep_think_llm": "gpt-4o",
    "quick_think_llm": "gpt-4o-mini",
    "temperature": 0.7,
    "llm_kwargs": {
        "max_tokens": 4096,
        "top_p": 0.9,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    }
}
```

### Model Recommendations by Use Case

#### Best for Cost Efficiency
- **Deep Think:** Ollama Llama 3 70B (local, free)
- **Quick Think:** Ollama Llama 3 8B (local, free)

#### Best for Quality
- **Deep Think:** GPT-4o or Claude 3 Opus
- **Quick Think:** GPT-4o-mini or Claude 3 Haiku

#### Best for Speed
- **Deep Think:** Groq Mixtral 8x7B
- **Quick Think:** Groq Llama 3 8B

#### Best for Privacy
- **Deep Think:** Ollama Llama 3 70B (local)
- **Quick Think:** Ollama Llama 3 8B (local)

## Troubleshooting

### Import Errors

If you get import errors for a specific provider:

```bash
pip install langchain-[provider]
```

For example:
```bash
pip install langchain-anthropic  # For Anthropic
pip install langchain-community  # For Ollama
pip install langchain-groq       # For Groq
```

### API Key Issues

Make sure your environment variables are set correctly:

```bash
# Check if set
echo $OPENAI_API_KEY

# Set temporarily
export OPENAI_API_KEY=your-key

# Set permanently (add to ~/.bashrc or ~/.zshrc)
echo 'export OPENAI_API_KEY=your-key' >> ~/.bashrc
```

### Ollama Connection Issues

If Ollama fails to connect:

1. Check if Ollama is running: `ollama list`
2. Verify the endpoint: Default is `http://localhost:11434`
3. Try pulling the model: `ollama pull llama3`

### Model Not Found

Make sure you're using the correct model identifier for each provider:

- OpenAI: `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`
- Anthropic: `claude-3-opus-20240229`, `claude-3-sonnet-20240229`, `claude-3-haiku-20240307`
- Google: `gemini-1.5-pro`, `gemini-1.5-flash`
- Ollama: `llama3`, `llama3:70b`, `mistral`, etc.

## Migration from OpenAI-Only Version

If you're upgrading from an older version that only supported OpenAI:

1. The default configuration still uses OpenAI, so existing code will work
2. To switch providers, update your config:
   ```python
   config["llm_provider"] = "ollama"  # or "anthropic", "google", etc.
   config["deep_think_llm"] = "llama3:70b"
   config["quick_think_llm"] = "llama3:8b"
   config["backend_url"] = "http://localhost:11434"
   ```
3. Install required packages for your chosen provider
4. Set appropriate environment variables

## Contributing

To add support for a new provider:

1. Edit `tradingagents/llm_factory.py`
2. Add a new `_create_[provider]_llm()` method
3. Update the `create_llm()` method to handle the new provider
4. Update this documentation
5. Submit a pull request
