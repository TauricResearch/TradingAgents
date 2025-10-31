# 🚀 Quick Start Guide - Multi-Provider AI Support

## What Changed?

Your TradingAgents project now supports **multiple AI providers** instead of just OpenAI! You can use:
- OpenAI (default - no changes needed)
- **Ollama (FREE local models!)**
- Anthropic Claude
- Google Gemini
- Groq, Azure, Together AI, and more

## For Existing Users

**Good news:** Your existing code still works! OpenAI is still the default.

```python
# This still works exactly as before
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(config=DEFAULT_CONFIG)
_, decision = ta.propagate("NVDA", "2024-05-10")
```

## Switching to Ollama (Free & Local)

Want to save money? Use local models with Ollama:

### Step 1: Install Ollama
```bash
# Visit https://ollama.ai and download for your OS
# Or on macOS/Linux:
curl -fsSL https://ollama.ai/install.sh | sh
```

### Step 2: Pull Models
```bash
ollama pull llama3:70b  # For deep thinking
ollama pull llama3:8b   # For quick tasks
```

### Step 3: Update Your Code
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create custom config for Ollama
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "llama3:70b"
config["quick_think_llm"] = "llama3:8b"
config["backend_url"] = "http://localhost:11434"

# Use it!
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
```

### Step 4: Install Python Package
```bash
pip install langchain-community
```

**That's it!** You're now using free local AI models. 🎉

## Switching to Other Providers

### Anthropic Claude
```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-3-opus-20240229"
config["quick_think_llm"] = "claude-3-haiku-20240307"

# Set API key
# export ANTHROPIC_API_KEY=sk-ant-your-key

ta = TradingAgentsGraph(config=config)
```

### Google Gemini
```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"
config["deep_think_llm"] = "gemini-1.5-pro"
config["quick_think_llm"] = "gemini-1.5-flash"

# Set API key
# export GOOGLE_API_KEY=your-google-key

ta = TradingAgentsGraph(config=config)
```

### Groq (Fast & Cheap)
```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "groq"
config["deep_think_llm"] = "mixtral-8x7b-32768"
config["quick_think_llm"] = "llama3-8b-8192"

# Set API key
# export GROQ_API_KEY=gsk-your-groq-key

# Install package
# pip install langchain-groq

ta = TradingAgentsGraph(config=config)
```

## Using Pre-Made Configs

Even easier - use the example configs:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from examples.llm_provider_configs import OLLAMA_CONFIG, ANTHROPIC_CONFIG

# Ollama
ollama_config = {**DEFAULT_CONFIG, **OLLAMA_CONFIG}
ta = TradingAgentsGraph(config=ollama_config)

# Anthropic
anthropic_config = {**DEFAULT_CONFIG, **ANTHROPIC_CONFIG}
ta = TradingAgentsGraph(config=anthropic_config)
```

## Quick Comparison

| Provider | Cost/Month | Speed | Quality | Privacy | Setup |
|----------|-----------|-------|---------|---------|-------|
| OpenAI | $50-200 | Medium | Excellent | Low | Easy |
| **Ollama** | **FREE** | **Fast** | **Good** | **Best** | **Medium** |
| Anthropic | $50-200 | Medium | Excellent | Low | Easy |
| Google | $20-100 | Fast | Very Good | Low | Easy |
| Groq | $10-50 | **Fastest** | Good | Low | Easy |

## Need Help?

📚 **Full Documentation:**
- [Complete Provider Guide](docs/LLM_PROVIDER_GUIDE.md) - Setup for all providers
- [Quick Examples](docs/MULTI_PROVIDER_SUPPORT.md) - Code snippets
- [Migration Guide](docs/MIGRATION_GUIDE.md) - Detailed changes

📝 **Example Configs:**
- `examples/llm_provider_configs.py` - Ready-to-use configurations

🧪 **Test It:**
```bash
python tests/test_multi_provider.py
```

## Common Questions

**Q: Will my existing code break?**
A: No! OpenAI is still the default. Your code works as-is.

**Q: Which provider should I use?**
A: 
- **Best for free:** Ollama
- **Best quality:** OpenAI GPT-4o or Claude 3 Opus
- **Best speed:** Groq
- **Best balance:** Google Gemini or Claude 3 Sonnet

**Q: Can I mix providers?**
A: Yes! Use cheap models for quick tasks, expensive for deep thinking.

**Q: Is my data safe?**
A: With Ollama, everything runs locally. With cloud providers, review their policies.

**Q: How do I get started with Ollama?**
A: Follow the 4 steps above. Takes ~10 minutes.

## What's Next?

1. ✅ Test your existing code (should work fine)
2. 🔧 Try Ollama to save money
3. 🎯 Experiment with different providers
4. 📊 Find the best balance for your needs

Enjoy your new flexibility! 🚀
