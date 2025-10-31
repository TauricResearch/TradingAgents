# Multi-Provider AI Support

This project has been updated to support multiple AI/LLM providers, making it provider-agnostic. You can now use:

- **OpenAI** (GPT-4, GPT-4o, GPT-3.5-turbo)
- **Ollama** (Local models - Llama 3, Mistral, Mixtral, etc.) - **FREE!**
- **Anthropic** (Claude 3 Opus, Sonnet, Haiku)
- **Google** (Gemini Pro, Gemini Flash)
- **Groq** (Fast inference for open-source models)
- **OpenRouter** (Multi-provider access)
- **Azure OpenAI**
- **Together AI**
- **HuggingFace**

## Quick Start Examples

### Using OpenAI (Default)

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# OpenAI is the default - just use it directly
ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2024-05-10")
```

### Using Ollama (Local, Free)

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create config for Ollama
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "llama3:70b"
config["quick_think_llm"] = "llama3:8b"
config["backend_url"] = "http://localhost:11434"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
```

### Using Anthropic Claude

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create config for Anthropic
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-3-opus-20240229"
config["quick_think_llm"] = "claude-3-haiku-20240307"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
```

### Using Google Gemini

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create config for Google
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"
config["deep_think_llm"] = "gemini-1.5-pro"
config["quick_think_llm"] = "gemini-1.5-flash"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
```

### Using Groq (Fast Inference)

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create config for Groq
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "groq"
config["deep_think_llm"] = "mixtral-8x7b-32768"
config["quick_think_llm"] = "llama3-8b-8192"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
```

## Using Example Configurations

The project includes pre-made configurations in `examples/llm_provider_configs.py`:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from examples.llm_provider_configs import OLLAMA_CONFIG, ANTHROPIC_CONFIG, GROQ_CONFIG

# Use Ollama
ollama_config = {**DEFAULT_CONFIG, **OLLAMA_CONFIG}
ta = TradingAgentsGraph(debug=True, config=ollama_config)

# Use Anthropic
anthropic_config = {**DEFAULT_CONFIG, **ANTHROPIC_CONFIG}
ta = TradingAgentsGraph(debug=True, config=anthropic_config)

# Use Groq
groq_config = {**DEFAULT_CONFIG, **GROQ_CONFIG}
ta = TradingAgentsGraph(debug=True, config=groq_config)
```

## Installation Notes

### Base Installation

The base installation includes support for OpenAI, Anthropic, and Google:

```bash
pip install -r requirements.txt
```

### Optional Provider Packages

For additional providers, install the specific package:

```bash
# For Ollama (local models)
pip install langchain-community

# For Groq
pip install langchain-groq

# For Together AI
pip install langchain-together
```

## Environment Variables

Set the appropriate API key for your chosen provider:

```bash
# OpenAI
export OPENAI_API_KEY=sk-your-key-here

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# Google
export GOOGLE_API_KEY=your-google-key-here

# Groq
export GROQ_API_KEY=gsk-your-groq-key

# Together AI
export TOGETHER_API_KEY=your-together-key

# Ollama (no API key needed - local)
# Just make sure Ollama is running: ollama serve
```

## Complete Documentation

For comprehensive documentation on all supported providers, configuration options, troubleshooting, and advanced usage, see:

📚 **[LLM Provider Configuration Guide](docs/LLM_PROVIDER_GUIDE.md)**

This guide includes:
- Detailed setup for each provider
- Model recommendations
- Cost optimization tips
- Troubleshooting common issues
- Advanced configuration options
