# Configuration Guide

Complete reference for configuring TradingAgents.

## Configuration File

Location: `tradingagents/default_config.py`

## Default Configuration

```python
DEFAULT_CONFIG = {
    # Directories
    "project_dir": "<auto-detected>",
    "results_dir": "./results",
    "data_cache_dir": "./dataflows/data_cache",

    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",

    # Workflow settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,

    # Data vendors
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "alpha_vantage",
        "news_data": "alpha_vantage"
    },

    # Tool-level overrides (optional)
    "tool_vendors": {}
}
```

## Configuration Options

### Directory Settings

#### project_dir
- **Type**: str
- **Default**: Auto-detected from package location
- **Description**: Root directory of TradingAgents package

#### results_dir
- **Type**: str
- **Default**: `"./results"`
- **Environment Variable**: `TRADINGAGENTS_RESULTS_DIR`
- **Description**: Directory for storing analysis results
- **Example**:
  ```python
  config["results_dir"] = "/path/to/results"
  # Or set environment variable
  export TRADINGAGENTS_RESULTS_DIR=/path/to/results
  ```

#### data_cache_dir
- **Type**: str
- **Default**: `"./dataflows/data_cache"`
- **Description**: Directory for caching data vendor responses

### LLM Settings

#### llm_provider
- **Type**: str
- **Options**: `"openai"`, `"anthropic"`, `"google"`, `"openrouter"`, `"ollama"`
- **Default**: `"openai"`
- **Description**: LLM provider selection

**Examples**:
```python
# OpenAI (default)
config["llm_provider"] = "openai"

# Anthropic
config["llm_provider"] = "anthropic"

# OpenRouter (unified access)
config["llm_provider"] = "openrouter"

# Google Generative AI
config["llm_provider"] = "google"

# Ollama (local)
config["llm_provider"] = "ollama"
```

#### deep_think_llm
- **Type**: str
- **Default**: `"o4-mini"`
- **Description**: Model for complex reasoning tasks
- **Use Cases**: Research debates, trading decisions, risk assessment

**Recommended Models by Provider**:
```python
# OpenAI
config["deep_think_llm"] = "o4-mini"  # Fast, affordable
config["deep_think_llm"] = "o1-preview"  # Best reasoning

# Anthropic
config["deep_think_llm"] = "claude-sonnet-4-20250514"

# OpenRouter
config["deep_think_llm"] = "anthropic/claude-sonnet-4.5"

# Google
config["deep_think_llm"] = "gemini-2.0-flash"

# Ollama
config["deep_think_llm"] = "mistral"
```

#### quick_think_llm
- **Type**: str
- **Default**: `"gpt-4o-mini"`
- **Description**: Model for fast, routine tasks
- **Use Cases**: Analyst reports, data summarization, tool calling

**Recommended Models**:
```python
# OpenAI
config["quick_think_llm"] = "gpt-4o-mini"  # Most cost-effective

# Anthropic
config["quick_think_llm"] = "claude-sonnet-4-20250514"

# OpenRouter
config["quick_think_llm"] = "openai/gpt-4o-mini"
```

#### backend_url
- **Type**: str
- **Default**: `"https://api.openai.com/v1"`
- **Description**: API endpoint for LLM provider

**Examples**:
```python
# OpenAI
config["backend_url"] = "https://api.openai.com/v1"

# Anthropic
config["backend_url"] = "https://api.anthropic.com"

# OpenRouter
config["backend_url"] = "https://openrouter.ai/api/v1"

# Ollama (local)
config["backend_url"] = "http://localhost:11434/v1"
```

### Workflow Settings

#### max_debate_rounds
- **Type**: int
- **Default**: `1`
- **Range**: 1-5
- **Description**: Number of bull/bear debate rounds
- **Impact**:
  - More rounds = deeper analysis
  - More rounds = higher cost and latency
  - Diminishing returns after 2-3 rounds

**Examples**:
```python
# Fast, cost-effective
config["max_debate_rounds"] = 1

# Balanced
config["max_debate_rounds"] = 2

# Deep analysis
config["max_debate_rounds"] = 3
```

#### max_risk_discuss_rounds
- **Type**: int
- **Default**: `1`
- **Range**: 1-3
- **Description**: Number of risk management discussion rounds

#### max_recur_limit
- **Type**: int
- **Default**: `100`
- **Description**: Maximum recursion limit for graph execution

### Data Vendor Settings

#### data_vendors
- **Type**: Dict[str, str]
- **Description**: Category-level data vendor configuration

**Available Categories**:

##### core_stock_apis
- **Options**: `"yfinance"`, `"alpha_vantage"`, `"local"`
- **Default**: `"yfinance"`
- **Purpose**: Stock prices and quotes

##### technical_indicators
- **Options**: `"yfinance"`, `"alpha_vantage"`, `"local"`
- **Default**: `"yfinance"`
- **Purpose**: Technical indicators (MACD, RSI, etc.)

##### fundamental_data
- **Options**: `"openai"`, `"alpha_vantage"`, `"local"`
- **Default**: `"alpha_vantage"`
- **Purpose**: Company financials and ratios

##### news_data
- **Options**: `"openai"`, `"alpha_vantage"`, `"google"`, `"local"`
- **Default**: `"alpha_vantage"`
- **Purpose**: News articles and events

**Example**:
```python
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "alpha_vantage",
    "news_data": "google"  # Use Google for news
}
```

#### tool_vendors
- **Type**: Dict[str, str]
- **Description**: Tool-level vendor overrides (takes precedence over categories)

**Example**:
```python
config["tool_vendors"] = {
    "get_stock_data": "alpha_vantage",  # Override category default
    "get_news": "google"  # Override category default
}
```

## Environment Variables

### LLM Provider API Keys

```bash
# OpenAI (required for OpenAI provider or embeddings)
export OPENAI_API_KEY=sk-your_key_here

# Anthropic (required for Anthropic provider)
export ANTHROPIC_API_KEY=sk-ant-your_key_here

# OpenRouter (required for OpenRouter provider)
export OPENROUTER_API_KEY=sk-or-v1-your_key_here

# Google (required for Google provider)
export GOOGLE_API_KEY=your_key_here
```

### Data Vendor API Keys

```bash
# Alpha Vantage (required for fundamental and news data)
export ALPHA_VANTAGE_API_KEY=your_key_here
```

### Application Settings

```bash
# Results directory
export TRADINGAGENTS_RESULTS_DIR=./results
```

## Configuration Examples

### Production Configuration

```python
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()

# Use production-grade models
config["llm_provider"] = "openai"
config["deep_think_llm"] = "o1-preview"  # Best reasoning
config["quick_think_llm"] = "gpt-4o"  # High quality

# Deep analysis
config["max_debate_rounds"] = 2
config["max_risk_discuss_rounds"] = 2

# Reliable data sources
config["data_vendors"] = {
    "core_stock_apis": "alpha_vantage",
    "technical_indicators": "alpha_vantage",
    "fundamental_data": "alpha_vantage",
    "news_data": "alpha_vantage"
}
```

### Development/Testing Configuration

```python
config = DEFAULT_CONFIG.copy()

# Use cost-effective models
config["llm_provider"] = "openai"
config["deep_think_llm"] = "o4-mini"
config["quick_think_llm"] = "gpt-4o-mini"

# Fast analysis
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1

# Free data sources
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "alpha_vantage",  # Free tier
    "news_data": "google"
}
```

### Cost-Optimized Configuration

```python
config = DEFAULT_CONFIG.copy()

# Use OpenRouter for competitive pricing
config["llm_provider"] = "openrouter"
config["deep_think_llm"] = "anthropic/claude-sonnet-4.5"
config["quick_think_llm"] = "openai/gpt-4o-mini"
config["backend_url"] = "https://openrouter.ai/api/v1"

# Minimal debate rounds
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
```

### Offline/Local Configuration

```python
config = DEFAULT_CONFIG.copy()

# Use local Ollama models
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "mistral"
config["quick_think_llm"] = "mistral"
config["backend_url"] = "http://localhost:11434/v1"

# Use local data cache
config["data_vendors"] = {
    "core_stock_apis": "local",
    "technical_indicators": "local",
    "fundamental_data": "local",
    "news_data": "local"
}
```

## Using Configuration

### In Code

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create custom config
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"
config["max_debate_rounds"] = 2

# Initialize with config
ta = TradingAgentsGraph(config=config)

# Run analysis
state, decision = ta.propagate("NVDA", "2024-05-10")
```

### In CLI

The CLI reads configuration from `default_config.py` and allows runtime overrides through the interactive menu.

### With .env File

Create `.env` file:

```env
# LLM Provider
OPENAI_API_KEY=sk-your_key_here
ANTHROPIC_API_KEY=sk-ant-your_key_here

# Data Vendor
ALPHA_VANTAGE_API_KEY=your_key_here

# Application
TRADINGAGENTS_RESULTS_DIR=./results
```

Load in Python:

```python
from dotenv import load_dotenv
load_dotenv()

# Now environment variables are available
```

## Best Practices

1. **Never Hardcode Keys**: Use environment variables
2. **Copy Default Config**: Always `config = DEFAULT_CONFIG.copy()`
3. **Start Minimal**: Use 1 debate round initially
4. **Test Locally**: Use Ollama for development
5. **Monitor Costs**: Track LLM API usage
6. **Cache Aggressively**: Use local data vendor when possible
7. **Validate Configuration**: Check keys before running

## Troubleshooting

### Missing API Keys

**Error**: `ValueError: OPENAI_API_KEY environment variable is required`

**Solution**:
```bash
export OPENAI_API_KEY=your_key_here
```

### Invalid Model Names

**Error**: `Invalid model name: 'gpt-5'`

**Solution**: Check provider documentation for valid model names

### Data Vendor Errors

**Error**: `VendorError: Alpha Vantage API key invalid`

**Solution**: Verify API key is correct and has remaining quota

## See Also

- [LLM Integration Architecture](../architecture/llm-integration.md)
- [Data Flow Architecture](../architecture/data-flow.md)
- [Adding LLM Provider](adding-llm-provider.md)
- [Quick Start Guide](../QUICKSTART.md)
