# README Addition - Multi-Provider AI Support

**Add this section to your README.md after the "Required APIs" section:**

---

## 🚀 NEW: Multi-Provider AI Support

TradingAgents now supports multiple AI/LLM providers! You're no longer limited to OpenAI.

**Supported Providers:**
- ✅ **OpenAI** (GPT-4, GPT-4o, GPT-3.5-turbo)
- ✅ **Ollama** (Local models - FREE! Llama 3, Mistral, Mixtral, etc.)
- ✅ **Anthropic** (Claude 3 Opus, Sonnet, Haiku)
- ✅ **Google** (Gemini Pro, Gemini Flash)
- ✅ **Groq** (Fast inference)
- ✅ **OpenRouter** (Multi-provider access)
- ✅ **Azure OpenAI**
- ✅ **Together AI**
- ✅ **HuggingFace**

📚 **[See Full Provider Guide](docs/LLM_PROVIDER_GUIDE.md)** | **[Quick Start Examples](docs/MULTI_PROVIDER_SUPPORT.md)**

### Quick Examples

**OpenAI (Default - No Changes Needed):**
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(config=DEFAULT_CONFIG)
_, decision = ta.propagate("NVDA", "2024-05-10")
```

**Ollama (Local & Free):**
```python
config = DEFAULT_CONFIG.copy()
config.update({
    "llm_provider": "ollama",
    "deep_think_llm": "llama3:70b",
    "quick_think_llm": "llama3:8b",
    "backend_url": "http://localhost:11434"
})
ta = TradingAgentsGraph(config=config)
```

**Anthropic Claude:**
```python
config = DEFAULT_CONFIG.copy()
config.update({
    "llm_provider": "anthropic",
    "deep_think_llm": "claude-3-opus-20240229",
    "quick_think_llm": "claude-3-haiku-20240307"
})
ta = TradingAgentsGraph(config=config)
```

**Google Gemini:**
```python
config = DEFAULT_CONFIG.copy()
config.update({
    "llm_provider": "google",
    "deep_think_llm": "gemini-1.5-pro",
    "quick_think_llm": "gemini-1.5-flash"
})
ta = TradingAgentsGraph(config=config)
```

**Groq (Fast & Affordable):**
```python
config = DEFAULT_CONFIG.copy()
config.update({
    "llm_provider": "groq",
    "deep_think_llm": "mixtral-8x7b-32768",
    "quick_think_llm": "llama3-8b-8192"
})
ta = TradingAgentsGraph(config=config)
```

See `examples/llm_provider_configs.py` for more pre-configured options!

---

**Then update the "Implementation Details" section to say:**

We built TradingAgents with LangGraph to ensure flexibility and modularity. The system now supports multiple LLM providers through a unified interface. You can use OpenAI (default), Ollama for local/free models, Anthropic Claude, Google Gemini, Groq, and others.

For OpenAI, we recommend using `o4-mini` and `gpt-4o-mini` for cost-effective testing, as our framework makes **lots of** API calls. For production, consider `o1-preview` and `gpt-4o`.

For free local inference, use Ollama with Llama 3 models. For the best quality, use Claude 3 Opus or GPT-4o. For the fastest inference, use Groq.

See the [LLM Provider Guide](docs/LLM_PROVIDER_GUIDE.md) for detailed recommendations and setup instructions.
