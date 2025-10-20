# TradingAgents Configuration Guide

**Complete guide to configuring TradingAgents for different scenarios**

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Configuration Methods](#configuration-methods)
3. [Deployment Scenarios](#deployment-scenarios)
4. [API Keys Setup](#api-keys-setup)
5. [Configuration Reference](#configuration-reference)
6. [CLI vs Module Usage](#cli-vs-module-usage)
7. [Environment Variables](#environment-variables)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Copy Environment Template

```bash
cp .env.example .env
```

### 2. Choose Your Scenario

Open `.env` and uncomment one of the scenarios:

- **Scenario 1**: OpenAI Everything (Recommended)
- **Scenario 2**: OpenRouter + OpenAI Embeddings (Cost Optimized)
- **Scenario 3**: All Local with Ollama (Offline/Private)
- **Scenario 4**: Anthropic + OpenAI Embeddings
- **Scenario 5**: Google Gemini + OpenAI Embeddings
- **Scenario 6**: OpenRouter + No Memory (Minimal)
- **Scenario 7**: Mixed Models (Advanced)

### 3. Add Your API Keys

Replace placeholder values with your actual API keys.

### 4. Run TradingAgents

**CLI Mode:**
```bash
python -m cli.main
```

**Module Mode:**
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

graph = TradingAgentsGraph(["market", "news"])
final_state, decision = graph.propagate("AAPL", "2025-01-15")
```

---

## Configuration Methods

### Method 1: Environment Variables (.env file)

**Best for**: CLI usage, development

```bash
# .env file
OPENAI_API_KEY=sk-proj-...
OPENROUTER_API_KEY=sk-or-v1-...
TRADINGAGENTS_LLM_PROVIDER=openrouter
```

The system automatically loads `.env` file on startup.

### Method 2: Config Dictionary (Python)

**Best for**: Module usage, programmatic control

```python
config = {
    "llm_provider": "openrouter",
    "backend_url": "https://openrouter.ai/api/v1",
    "deep_think_llm": "deepseek/deepseek-chat-v3-0324:free",
    "quick_think_llm": "meta-llama/llama-3.3-8b-instruct:free",
    
    "embedding_provider": "openai",
    "embedding_backend_url": "https://api.openai.com/v1",
    "enable_memory": True,
}

graph = TradingAgentsGraph(["market"], config=config)
```

### Method 3: CLI Interactive

**Best for**: Quick testing, exploration

```bash
python -m cli.main
```

Follow the interactive prompts to select:
- Ticker symbol
- Analysis date
- Analysts team
- Research depth
- LLM provider
- Thinking agents
- Embedding provider

---

## Deployment Scenarios

### Scenario 1: OpenAI Everything ⭐ Recommended

**Use Case**: Production deployment with full features

**Configuration:**

```bash
# .env
OPENAI_API_KEY=sk-proj-your_key_here
ALPHA_VANTAGE_API_KEY=your_key_here
```

**Pros:**
- ✅ Full feature support
- ✅ Reliable and fast
- ✅ Single provider simplicity

**Cons:**
- 💰 Moderate cost (chat + embeddings)

**Cost**: ~$0.50-$2.00 per analysis (depending on depth)

---

### Scenario 2: OpenRouter + OpenAI Embeddings 💰 Cost Optimized

**Use Case**: Development, testing, cost optimization

**Configuration:**

```bash
# .env
OPENROUTER_API_KEY=sk-or-v1-your_key_here
OPENAI_API_KEY=sk-proj-your_key_here
ALPHA_VANTAGE_API_KEY=your_key_here

TRADINGAGENTS_LLM_PROVIDER=openrouter
TRADINGAGENTS_BACKEND_URL=https://openrouter.ai/api/v1
TRADINGAGENTS_EMBEDDING_PROVIDER=openai
TRADINGAGENTS_EMBEDDING_BACKEND_URL=https://api.openai.com/v1
```

**Pros:**
- ✅ Very low cost (free chat models)
- ✅ Full memory/embedding support
- ✅ Good for development

**Cons:**
- ⚠️ Free models may be slower
- ⚠️ Quality varies by model

**Cost**: ~$0.05-$0.20 per analysis (embeddings only)

---

### Scenario 3: All Local with Ollama 🔒 Privacy First

**Use Case**: Offline deployment, privacy requirements, no API costs

**Prerequisites:**

```bash
# Install Ollama
# Visit: https://ollama.ai

# Pull required models
ollama pull llama3.1
ollama pull llama3.2
ollama pull nomic-embed-text
```

**Configuration:**

```bash
# .env
ALPHA_VANTAGE_API_KEY=your_key_here

TRADINGAGENTS_LLM_PROVIDER=ollama
TRADINGAGENTS_BACKEND_URL=http://localhost:11434/v1
TRADINGAGENTS_EMBEDDING_PROVIDER=ollama
TRADINGAGENTS_EMBEDDING_BACKEND_URL=http://localhost:11434/v1
TRADINGAGENTS_EMBEDDING_MODEL=nomic-embed-text
```

**Pros:**
- ✅ Completely free
- ✅ Full privacy (no data leaves your machine)
- ✅ Works offline
- ✅ No rate limits

**Cons:**
- ⚠️ Requires local compute resources
- ⚠️ Slower than cloud APIs
- ⚠️ Quality depends on local model

**Cost**: $0 (requires GPU for best performance)

---

### Scenario 4: Anthropic + OpenAI Embeddings 🧠 High Quality

**Use Case**: High-quality reasoning and analysis

**Configuration:**

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-your_key_here
OPENAI_API_KEY=sk-proj-your_key_here
ALPHA_VANTAGE_API_KEY=your_key_here

TRADINGAGENTS_LLM_PROVIDER=anthropic
TRADINGAGENTS_BACKEND_URL=https://api.anthropic.com/
TRADINGAGENTS_EMBEDDING_PROVIDER=openai
TRADINGAGENTS_EMBEDDING_BACKEND_URL=https://api.openai.com/v1
```

**Pros:**
- ✅ Excellent reasoning (Claude)
- ✅ Long context support
- ✅ High-quality outputs

**Cons:**
- 💰 Higher cost

**Cost**: ~$1.00-$5.00 per analysis (depending on model)

---

### Scenario 5: Google Gemini + OpenAI Embeddings 📊 Balanced

**Use Case**: Cost-effective with good performance

**Configuration:**

```bash
# .env
GOOGLE_API_KEY=your_key_here
OPENAI_API_KEY=sk-proj-your_key_here
ALPHA_VANTAGE_API_KEY=your_key_here

TRADINGAGENTS_LLM_PROVIDER=google
TRADINGAGENTS_EMBEDDING_PROVIDER=openai
```

**Pros:**
- ✅ Good quality/cost ratio
- ✅ Fast response times
- ✅ Multimodal capabilities

**Cons:**
- ⚠️ Newer, less tested in production

**Cost**: ~$0.30-$1.00 per analysis

---

### Scenario 6: OpenRouter + No Memory 🚀 Minimal

**Use Case**: Testing, debugging, minimal cost

**Configuration:**

```bash
# .env
OPENROUTER_API_KEY=sk-or-v1-your_key_here
ALPHA_VANTAGE_API_KEY=your_key_here

TRADINGAGENTS_LLM_PROVIDER=openrouter
TRADINGAGENTS_BACKEND_URL=https://openrouter.ai/api/v1
TRADINGAGENTS_ENABLE_MEMORY=false
```

**Pros:**
- ✅ Minimal cost
- ✅ Fast setup
- ✅ No embedding API needed

**Cons:**
- ⚠️ No historical context
- ⚠️ Agents can't learn from past decisions

**Cost**: ~$0.00-$0.10 per analysis (free models)

---

### Scenario 7: Mixed Models 🎛️ Advanced

**Use Case**: Optimize for specific use cases

**Configuration:**

```bash
# .env
# Cheap chat models
OPENROUTER_API_KEY=sk-or-v1-your_key_here
TRADINGAGENTS_LLM_PROVIDER=openrouter
TRADINGAGENTS_DEEP_THINK_LLM=deepseek/deepseek-chat-v3-0324:free
TRADINGAGENTS_QUICK_THINK_LLM=meta-llama/llama-3.3-8b-instruct:free

# Reliable embeddings
OPENAI_API_KEY=sk-proj-your_key_here
TRADINGAGENTS_EMBEDDING_PROVIDER=openai
TRADINGAGENTS_EMBEDDING_MODEL=text-embedding-3-small

# Data sources
ALPHA_VANTAGE_API_KEY=your_key_here
```

**Pros:**
- ✅ Maximum flexibility
- ✅ Optimize each component
- ✅ Balance cost/performance

**Cons:**
- ⚠️ More complex setup
- ⚠️ Multiple API keys required

**Cost**: Varies based on choices

---

## API Keys Setup

### OpenAI

1. Visit: https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy key (format: `sk-proj-...`)
4. Add to `.env`: `OPENAI_API_KEY=sk-proj-...`

**Used for**: Chat models, embeddings

### OpenRouter

1. Visit: https://openrouter.ai/keys
2. Create account and generate key
3. Copy key (format: `sk-or-v1-...`)
4. Add to `.env`: `OPENROUTER_API_KEY=sk-or-v1-...`

**Used for**: Chat models (many providers)

### Anthropic

1. Visit: https://console.anthropic.com/
2. Navigate to API Keys
3. Create new key (format: `sk-ant-...`)
4. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`

**Used for**: Claude chat models

### Google

1. Visit: https://makersuite.google.com/app/apikey
2. Create API key
3. Copy key (format: `AI...`)
4. Add to `.env`: `GOOGLE_API_KEY=AI...`

**Used for**: Gemini chat models

### Alpha Vantage

1. Visit: https://www.alphavantage.co/support/#api-key
2. Get free API key
3. Add to `.env`: `ALPHA_VANTAGE_API_KEY=...`

**Used for**: Financial data, news

---

## Configuration Reference

### Complete Config Dictionary

```python
config = {
    # LLM Provider Settings
    "llm_provider": "openai",                    # openai, openrouter, anthropic, google, ollama
    "backend_url": "https://api.openai.com/v1",
    "deep_think_llm": "o4-mini",                 # Model for deep reasoning
    "quick_think_llm": "gpt-4o-mini",            # Model for quick tasks
    
    # Embedding Settings (Separate from chat)
    "embedding_provider": "openai",              # openai, ollama, none
    "embedding_backend_url": "https://api.openai.com/v1",
    "embedding_model": "text-embedding-3-small",
    "enable_memory": True,                       # Enable/disable memory system
    
    # Logging Settings
    "log_level": "INFO",                         # DEBUG, INFO, WARNING, ERROR, CRITICAL
    "log_dir": "logs",
    "log_to_console": True,
    "log_to_file": True,
    
    # Research Settings
    "max_debate_rounds": 1,                      # 1-5, higher = deeper analysis
    "max_risk_discuss_rounds": 1,                # 1-5, higher = more thorough risk assessment
    
    # Data Vendor Settings
    "data_vendors": {
        "core_stock_apis": "yfinance",           # yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",
        "fundamental_data": "alpha_vantage",
        "news_data": "alpha_vantage",
    },
    
    # Directory Settings
    "project_dir": ".",
    "results_dir": "./results",
    "data_cache_dir": "./dataflows/data_cache",
}
```

---

## CLI vs Module Usage

### CLI Usage (Interactive)

**When to use**: Quick analysis, exploration, non-technical users

**Run:**
```bash
python -m cli.main
```

**Workflow:**
1. Select ticker (e.g., AAPL)
2. Select date
3. Choose analysts (market, news, fundamentals, social)
4. Choose research depth (shallow, medium, deep)
5. Choose LLM provider (OpenAI, OpenRouter, Anthropic, Google, Ollama)
6. Choose thinking agents (quick/deep models)
7. Choose embedding provider (OpenAI, Ollama, Disable)

**Configuration:**
- API keys from `.env` file
- Prompts guide you through options
- Results saved to `results/` directory

### Module Usage (Programmatic)

**When to use**: Automation, integration, batch processing

**Example:**

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from datetime import datetime

# Configure
config = {
    "llm_provider": "openrouter",
    "backend_url": "https://openrouter.ai/api/v1",
    "deep_think_llm": "deepseek/deepseek-chat-v3-0324:free",
    "quick_think_llm": "meta-llama/llama-3.3-8b-instruct:free",
    "embedding_provider": "openai",
    "embedding_backend_url": "https://api.openai.com/v1",
    "enable_memory": True,
    "log_level": "INFO",
}

# Initialize
graph = TradingAgentsGraph(
    selected_analysts=["market", "news", "fundamentals"],
    config=config,
    debug=False
)

# Run analysis
tickers = ["AAPL", "GOOGL", "MSFT"]
for ticker in tickers:
    final_state, decision = graph.propagate(ticker, datetime.now().strftime("%Y-%m-%d"))
    print(f"{ticker}: {decision}")
    
    # Optionally reflect on results
    # graph.reflect_and_remember(returns_losses)
```

**Configuration:**
- Full control in code
- No interactive prompts
- Ideal for automation

---

## Environment Variables

### Provider Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `TRADINGAGENTS_LLM_PROVIDER` | Chat LLM provider | `openrouter` |
| `TRADINGAGENTS_BACKEND_URL` | Chat API endpoint | `https://openrouter.ai/api/v1` |
| `TRADINGAGENTS_DEEP_THINK_LLM` | Deep reasoning model | `deepseek/deepseek-chat-v3-0324:free` |
| `TRADINGAGENTS_QUICK_THINK_LLM` | Quick thinking model | `meta-llama/llama-3.3-8b-instruct:free` |

### Embedding Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `TRADINGAGENTS_EMBEDDING_PROVIDER` | Embedding provider | `openai` |
| `TRADINGAGENTS_EMBEDDING_BACKEND_URL` | Embedding API endpoint | `https://api.openai.com/v1` |
| `TRADINGAGENTS_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `TRADINGAGENTS_ENABLE_MEMORY` | Enable memory system | `true` or `false` |

### Logging Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `TRADINGAGENTS_LOG_LEVEL` | Logging verbosity | `INFO` |
| `TRADINGAGENTS_LOG_DIR` | Log directory | `logs` |
| `TRADINGAGENTS_LOG_TO_CONSOLE` | Console logging | `true` |
| `TRADINGAGENTS_LOG_TO_FILE` | File logging | `true` |

---

## Troubleshooting

### Issue: No auth credentials found

**Error:**
```
AuthenticationError: Error code: 401 - {'error': {'message': 'No auth credentials found'}}
```

**Solution:**
1. Check if API key is set in `.env`
2. Verify key format (e.g., `sk-proj-...` for OpenAI)
3. Run environment checker:
   ```bash
   python3 check_env_setup.py
   ```

### Issue: Failed to get embedding

**Error:**
```
ERROR | MEMORY | Failed to get embedding: 401 Unauthorized
```

**Solution:**
1. Set `OPENAI_API_KEY` if using OpenAI for embeddings
2. OR set `TRADINGAGENTS_ENABLE_MEMORY=false` to disable
3. OR use Ollama for local embeddings

### Issue: Memory disabled unexpectedly

**Logs:**
```
WARNING | MEMORY | Memory disabled for 'bull_memory'
```

**Solution:**
1. Check `TRADINGAGENTS_ENABLE_MEMORY=true`
2. Verify embedding provider is valid
3. Check embedding API key is set

### Issue: Wrong provider selected

**Error:**
```
Unsupported LLM provider: xyz
```

**Solution:**
1. Check `TRADINGAGENTS_LLM_PROVIDER` value
2. Valid options: `openai`, `openrouter`, `anthropic`, `google`, `ollama`
3. Case-sensitive!

### Issue: Module not found

**Error:**
```
ModuleNotFoundError: No module named 'tradingagents'
```

**Solution:**
```bash
# Install in development mode
pip install -e .

# Or install dependencies
pip install -r requirements.txt
```

---

## Verification Checklist

Before running TradingAgents, verify:

- [ ] `.env` file exists (copied from `.env.example`)
- [ ] API keys are set correctly
- [ ] Provider configuration matches your API keys
- [ ] Embedding provider is configured if memory enabled
- [ ] Log directory is writable
- [ ] Dependencies are installed

**Quick check:**
```bash
python3 check_env_setup.py
```

---

## Best Practices

### Development

```bash
# Use cost-optimized setup
OPENROUTER_API_KEY=sk-or-v1-...
OPENAI_API_KEY=sk-proj-...
TRADINGAGENTS_LLM_PROVIDER=openrouter
TRADINGAGENTS_EMBEDDING_PROVIDER=openai
TRADINGAGENTS_LOG_LEVEL=DEBUG
```

### Production

```bash
# Use reliable providers
OPENAI_API_KEY=sk-proj-...
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_LOG_LEVEL=INFO
TRADINGAGENTS_LOG_TO_FILE=true
```

### Testing/CI

```bash
# Disable expensive features
OPENROUTER_API_KEY=sk-or-v1-...
TRADINGAGENTS_LLM_PROVIDER=openrouter
TRADINGAGENTS_ENABLE_MEMORY=false
TRADINGAGENTS_LOG_LEVEL=WARNING
```

---

## Security Notes

1. **Never commit `.env` to git**
   ```bash
   # Add to .gitignore
   echo ".env" >> .gitignore
   ```

2. **Use separate keys for dev/prod**

3. **Rotate keys regularly**

4. **Monitor API usage**
   - Set spending limits in provider dashboards
   - Review `logs/api_calls.log` for usage tracking

5. **Use least-privilege keys**
   - Restrict key permissions when possible

---

## Support

For more help:

- **Environment Setup**: `check_env_setup.py`
- **Embedding Configuration**: `docs/EMBEDDING_CONFIGURATION.md`
- **Logging System**: `docs/LOGGING.md`
- **Feature Overview**: `FEATURE_EMBEDDING_README.md`

---

**Last Updated**: 2025-01-15  
**Version**: 2.0  
**Status**: Production Ready ✅