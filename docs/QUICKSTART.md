# Quick Start Guide

Get started with TradingAgents in under 10 minutes.

## Installation

### Prerequisites

- Python >= 3.10 (Python 3.13 recommended)
- pip package manager
- Conda or virtualenv (recommended)

### Step 1: Clone the Repository

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

### Step 2: Create Virtual Environment

Using conda (recommended):

```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

Or using venv:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

## Required APIs

TradingAgents requires API keys for LLM providers and data sources.

### LLM Provider (choose one)

**Option 1: OpenAI (default)**

```bash
export OPENAI_API_KEY=your_api_key_here
```

Get your key at: [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)

**Option 2: Anthropic**

```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

Get your key at: [https://console.anthropic.com/](https://console.anthropic.com/)

**Option 3: OpenRouter (unified access)**

```bash
export OPENROUTER_API_KEY=your_api_key_here
export OPENAI_API_KEY=your_api_key_here  # Still needed for embeddings
```

Get your key at: [https://openrouter.ai/keys](https://openrouter.ai/keys)

**Option 4: Google Generative AI**

```bash
export GOOGLE_API_KEY=your_api_key_here
```

Get your key at: [https://makersuite.google.com/app/apikey](https://makersuite.google.com/app/apikey)

### Data Vendor

**Alpha Vantage (required for fundamental and news data)**

```bash
export ALPHA_VANTAGE_API_KEY=your_api_key_here
```

Get a free key at: [https://www.alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key)

TradingAgents users get increased rate limits (60 requests/minute, no daily limits) thanks to Alpha Vantage's open-source support program.

### Using .env File

Alternatively, create a `.env` file in the project root:

```bash
cp .env.example .env
# Edit .env with your actual API keys
```

Example `.env`:

```env
OPENAI_API_KEY=your_openai_key_here
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here
TRADINGAGENTS_RESULTS_DIR=./results
```

## Your First Analysis

### CLI Mode

Run the interactive CLI:

```bash
python -m cli.main
```

You'll see a menu where you can:
- Select ticker symbols (e.g., NVDA, AAPL, TSLA)
- Choose analysis date
- Configure LLM models
- Set research depth (debate rounds)

The CLI will display real-time progress as agents analyze the market and generate trading signals.

### Programmatic Mode

Create a Python script:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Initialize the trading graph
ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# Run analysis for NVDA on a specific date
_, decision = ta.propagate("NVDA", "2024-05-10")

# Print the trading decision
print(f"Decision: {decision['action']}")
print(f"Confidence: {decision['confidence_score']}")
print(f"Reasoning: {decision['reasoning']}")
```

Run your script:

```bash
python your_script.py
```

## Configuration

### Using Different LLM Providers

**OpenAI (default):**

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["deep_think_llm"] = "o4-mini"
config["quick_think_llm"] = "gpt-4o-mini"
config["backend_url"] = "https://api.openai.com/v1"
```

**Anthropic:**

```python
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-sonnet-4-20250514"
config["quick_think_llm"] = "claude-sonnet-4-20250514"
config["backend_url"] = "https://api.anthropic.com"
```

**OpenRouter:**

```python
config["llm_provider"] = "openrouter"
config["deep_think_llm"] = "anthropic/claude-sonnet-4.5"
config["quick_think_llm"] = "openai/gpt-4o-mini"
config["backend_url"] = "https://openrouter.ai/api/v1"
```

### Customizing Data Vendors

```python
config["data_vendors"] = {
    "core_stock_apis": "yfinance",        # Stock prices
    "technical_indicators": "yfinance",   # Technical analysis
    "fundamental_data": "alpha_vantage",  # Company fundamentals
    "news_data": "alpha_vantage",         # News and sentiment
}
```

See [Configuration Guide](guides/configuration.md) for all available options.

## Next Steps

- **[Architecture Overview](architecture/multi-agent-system.md)** - Understand how agents work together
- **[API Reference](api/trading-graph.md)** - Explore the full API
- **[Adding New Analysts](guides/adding-new-analyst.md)** - Extend the framework
- **[Configuration Guide](guides/configuration.md)** - Advanced configuration options

## Troubleshooting

### Common Issues

**API Rate Limits**

If you hit rate limits, the framework will automatically save partial analysis state. Wait for the suggested retry time and re-run.

**Missing API Keys**

Ensure environment variables are set:

```bash
echo $OPENAI_API_KEY
echo $ALPHA_VANTAGE_API_KEY
```

**Import Errors**

Ensure you're in the correct virtual environment:

```bash
conda activate tradingagents  # or source venv/bin/activate
```

**Data Vendor Errors**

Check your Alpha Vantage API key is valid and has remaining quota. Free tier allows 25 requests/day; TradingAgents users get 60 requests/minute.

## Getting Help

- **Documentation**: Browse the [full documentation](README.md)
- **Discord**: Join our [Discord community](https://discord.com/invite/hk9PGKShPK)
- **GitHub Issues**: [Report bugs or ask questions](https://github.com/TauricResearch/TradingAgents/issues)

Happy trading!
