# TradingAgents: Multi-Agents LLM Financial Trading Framework

## Fork Status

This project is an independent fork of `TauricResearch/TradingAgents` with selective upstream sync.

The fork keeps the original multi-agent trading analysis foundation, but its direction is now independent. Development focuses on this repository's own report workflow, analyst experience, provider support, documentation, and operational needs.

Selective upstream sync means upstream bug fixes, security fixes, and useful infrastructure improvements may be pulled in when they fit this fork. This project does not aim to mirror upstream feature direction or preserve strict drop-in compatibility.

A detailed explainer on [how it works](TICKER_REPORT_ANALYST_GUIDE.md) is available.

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Install & Run](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

## TradingAgents Framework

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents: from fundamental analysts, sentiment experts, and technical analysts, to trader, risk management team, the platform collaboratively evaluates market conditions and informs trading decisions. Moreover, these agents engage in dynamic discussions to pinpoint the optimal strategy.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

Our framework decomposes complex trading tasks into specialized roles. This ensures the system achieves a robust, scalable approach to market analysis and decision-making.

### Analyst Team

- Fundamentals Analyst: Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags.
- Sentiment Analyst: Analyzes social media and public sentiment using sentiment scoring algorithms to gauge short-term market mood.
- News Analyst: Monitors global news and macroeconomic indicators, interpreting the impact of events on market conditions.
- Technical Analyst: Utilizes technical indicators (like MACD and RSI) to detect trading patterns and forecast price movements.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team

- Comprises both bullish and bearish researchers who critically assess the insights provided by the Analyst Team. Through structured debates, they balance potential gains against inherent risks.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Trader Agent

- Composes reports from the analysts and researchers to make informed trading decisions. It determines the timing and magnitude of trades based on comprehensive market insights.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Risk Management and Portfolio Manager

- Continuously evaluates portfolio risk by assessing market volatility, liquidity, and other risk factors. The risk management team evaluates and adjusts trading strategies, providing assessment reports to the Portfolio Manager for final decision.
- The Portfolio Manager approves/rejects the transaction proposal. If approved, the order will be sent to the simulated exchange and executed.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation and CLI

### Installation

Clone TradingAgents:

```bash
git clone https://github.com/skanga/TradingAgents.git
cd TradingAgents
```

Create a project-local virtual environment with Python 3.13:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
./.venv/Scripts/activate
```

Install the package and its dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run it interactively (you will be prompted for everything)

```bash
python -m cli.main
```

Common development checks:

```powershell
# Run the full test suite
python -m pytest

# Run a focused test file
python -m pytest tests/test_cli_llm_config.py -v

# Lint
ruff check .

# Static type check
mypy .
```

### Docker

Alternatively, run with Docker:

```bash
cp .env.example .env  # add your API keys
docker compose run --rm tradingagents
```

For local models with Ollama:

```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

### Required APIs

TradingAgents supports multiple LLM providers. Set the API key for your chosen provider:

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export DEEPSEEK_API_KEY=...        # DeepSeek
export DASHSCOPE_API_KEY=...       # Qwen (Alibaba DashScope)
export ZHIPU_API_KEY=...           # GLM (Zhipu)
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
```

For enterprise providers (e.g. Azure OpenAI, AWS Bedrock), copy `.env.enterprise.example` to `.env.enterprise` and fill in your credentials.

For local models, configure Ollama with `llm_provider: "ollama"` in your config.

Alternatively, copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

LLM runtime settings can come from CLI options or `.env` variables. CLI options take precedence over `.env` and environment variables. When `llm_provider`, `quick_model`, and `deep_model` are already configured, the interactive TUI skips the provider/model prompts and only asks for unrelated run settings such as ticker, date, analysts, and research depth.

Supported runtime env vars:

```bash
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_QUICK_MODEL=gpt-5.4-mini
TRADINGAGENTS_DEEP_MODEL=gpt-5.4
TRADINGAGENTS_BACKEND_URL=
TRADINGAGENTS_OPENAI_REASONING_EFFORT=
TRADINGAGENTS_GOOGLE_THINKING_LEVEL=
TRADINGAGENTS_ANTHROPIC_EFFORT=
```

For any unknown OpenAI-compatible endpoint (like InceptionLabs in this case), use the OpenAI provider with a custom base URL:

```bash
tradingagents \
  --ticker SPY \
  --analysis-date today \
  --output-language English \
  --analysts market,news,fundamentals \
  --research-depth 3 \
  --llm-provider openai \
  --backend-url https://api.inceptionlabs.ai/v1 \
  --quick-model mercury-2 \
  --deep-model mercury-2 \
  --save-report \
  --save-path reports/spy \
  --no-display-report
```

When all pre-analysis options are supplied, the CLI skips the setup prompts and starts the analysis directly.
Use `--analysis-date today` to resolve the date at runtime, or pass an explicit `YYYY-MM-DD` value for reproducible historical runs.

Run a holdings-aware batch analysis from a portfolio CSV or JSON file:

```bash
tradingagents batch \
  --input portfolio.csv \
  --analysis-date today \
  --output-language English \
  --analysts market,news,fundamentals \
  --research-depth 1 \
  --llm-provider openai \
  --quick-model gpt-5.4-mini \
  --deep-model gpt-5.4 \
  --save-path reports/batch_tech \
  --no-display-report
```

Batch CSV and JSON inputs must include `ticker` and may include `quantity`, `average_cost`, `market_value`, `target_weight`, and `notes`. Each ticker gets its own report bundle, and the batch directory also includes `batch_summary.md`, `batch_summary.html`, and `batch_results.json`.

Generate a portfolio allocation plan from the batch results:

```bash
tradingagents batch --input portfolio.csv --cash 2500 --allocate
tradingagents batch --tickers AAPL,MSFT,NVDA --cash 5000 --allocate --dry-run
tradingagents batch --input portfolio.csv --cash 5000 --allocate --max-position-weight 0.20 --min-cash-weight 0.05
```

Allocation mode ranks successful ticker analyses, computes current and target portfolio weights, sizes whole-share buy/sell deltas when prices can be derived from `market_value / quantity`, and keeps uninvestable remainder as leftover cash. `--dry-run` prints planned paper orders only; it does not submit broker orders. Allocation outputs are generated research tooling, not financial advice.

When `--allocate` is enabled, the batch output directory also includes `allocation_plan.md`, `allocation_plan.html`, and `allocation_plan.json`.

The same setup can live in the `.env` file instead - this example uses groq:

```bash
OPENAI_API_KEY=...
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_BACKEND_URL=https://api.groq.com/openai/v1
TRADINGAGENTS_QUICK_MODEL=openai/gpt-oss-20b
TRADINGAGENTS_DEEP_MODEL=openai/gpt-oss-120b
```

Custom OpenAI-compatible base URLs use the Chat Completions-compatible path and accept unknown model IDs without catalog validation warnings.

### CLI Usage

Launch the interactive CLI:

```bash
tradingagents          # installed command
python -m cli.main     # alternative: run directly from source
```

You will see a screen where you can select your desired tickers, analysis date, LLM provider, research depth, and more.

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

An interface will appear showing results as they load, letting you track the agent's progress as it runs.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## TradingAgents Package

### Implementation Details

We built TradingAgents with LangGraph to ensure flexibility and modularity. The framework supports multiple LLM providers: OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen (Alibaba DashScope), GLM (Zhipu), OpenRouter, Ollama for local models, and Azure OpenAI for enterprise.

### Python Usage

To use TradingAgents inside your code, you can import the `tradingagents` module and initialize a `TradingAgentsGraph()` object. The `.propagate()` function will return a decision. You can run `main.py`, here's also a quick example:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, etc.

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # openai, google, anthropic, xai, deepseek, qwen, glm, openrouter, ollama, azure
config["deep_think_llm"] = "gpt-5.4"     # Model for complex reasoning
config["quick_think_llm"] = "gpt-5.4-mini" # Model for quick tasks
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

See `tradingagents/default_config.py` for all configuration options.

For an OpenAI-compatible provider that is not listed in the model catalog, keep `llm_provider` as `openai` and set `backend_url`:

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["backend_url"] = "https://api.inceptionlabs.ai/v1"
config["quick_think_llm"] = "mercury"
config["deep_think_llm"] = "mercury"
```

## Persistence and Recovery

TradingAgents persists two kinds of state across runs.

### Decision log

The decision log is always on. Each completed run appends its decision to `~/.tradingagents/memory/trading_memory.md`. On the next run for the same ticker, TradingAgents fetches the realised return (raw and alpha vs SPY), generates a one-paragraph reflection, and injects the most recent same-ticker decisions plus recent cross-ticker lessons into the Portfolio Manager prompt, so each analysis carries forward what worked and what didn't.

Override the path with `TRADINGAGENTS_MEMORY_LOG_PATH`.

### Checkpoint resume

Checkpoint resume is opt-in via `--checkpoint`. When enabled, LangGraph saves state after each node so a crashed or interrupted run resumes from the last successful step instead of starting over. On a resume run you will see `Resuming from step N for <TICKER> on <date>` in the logs; on a new run you will see `Starting fresh`. Checkpoints are cleared automatically on successful completion.

Per-ticker SQLite databases live at `~/.tradingagents/cache/checkpoints/<TICKER>.db` (override the base with `TRADINGAGENTS_CACHE_DIR`). Use `--clear-checkpoints` to reset all of them before a run.

```bash
tradingagents analyze --checkpoint           # enable for this run
tradingagents analyze --clear-checkpoints    # reset before running
```

```python
config = DEFAULT_CONFIG.copy()
config["checkpoint_enabled"] = True
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
```

## Contributing

We welcome contributions from the community! Whether it's fixing a bug, improving documentation, or suggesting a new feature, your input helps make this project better. If you are interested in this line of research, please consider joining our open-source financial AI research community [Tauric Research](https://tauric.ai/).

Past contributions, including code, design feedback, and bug reports, are credited per release in [`CHANGELOG.md`](CHANGELOG.md).

## Citation

Please reference our work if you find *TradingAgents* provides you with some help :)

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```
