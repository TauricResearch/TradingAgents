<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="./assets/wechat.png" target="_blank"><img alt="WeChat" src="https://img.shields.io/badge/WeChat-TauricResearch-brightgreen?logo=wechat&logoColor=white"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <br>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/Join_GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>

<div align="center">
  <!-- Keep these links. Translations will automatically update with the README. -->
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=de">Deutsch</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=es">Español</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=fr">français</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ja">日本語</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ko">한국어</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=zh">中文</a>
</div>

---

# TradingAgents: Multi-Agents LLM Financial Trading Framework

## News
- [2026-03] **Major Architectural Upgrade**: Integrated **Multi-Round Risk Debate**, **Heuristic Summarization** (50% latency reduction), and **Scanner Context Ground-Truth** to eliminate LLM hallucinations on commodity prices and catalyst dates.
- [2026-03] **TradingAgents v0.2.2** released with GPT-5.4/Gemini 3.1/Claude 4.6 model coverage, five-tier rating scale, OpenAI Responses API, Anthropic effort control, and cross-platform stability.
- [2026-02] **TradingAgents v0.2.0** released with multi-provider LLM support (GPT-5.x, Gemini 3.x, Claude 4.x, Grok 4.x) and improved system architecture.
- [2026-01] **Trading-R1** [Technical Report](https://arxiv.org/abs/2509.11420) released, with [Terminal](https://github.com/TauricResearch/Trading-R1) expected to land soon.

<div align="center">
<a href="https://www.star-history.com/#TauricResearch/TradingAgents&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" />
   <img alt="TradingAgents Star History" src="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>

> 🎉 **TradingAgents** officially released! We have received numerous inquiries about the work, and we would like to express our thanks for the enthusiasm in our community.
>
> So we decided to fully open-source the framework. Looking forward to building impactful projects with you!

<div align="center">

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

## Project Description

TradingAgents is an advanced, fully open-source multi-agent LLM framework designed to mirror the complex dynamics and decision-making processes of real-world financial trading firms. By leveraging multiple specialized LLMs powered by LangGraph, the platform continuously scans macro-economic conditions, evaluates market sentiment, and conducts deep-dive analysis on individual stocks. 

The system orchestrates dynamic debates among LLM-driven researchers—balancing bullish and bearish perspectives to arrive at high-conviction trading signals. It acts as an end-to-end automated research and portfolio management pipeline built for the AI era.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> **Disclaimer:** TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

## Architecture Overview

Our framework is fundamentally built on top of LangGraph for robust state management and multi-node orchestration. It decomposes complex trading tasks into specialized domains to ensure scalable, hallucination-resistant analysis.

### 1. Market Scanner Pipeline
Before individual stocks are selected, the **Scanner Pipeline** automatically identifies key macro trends, geopolitical events, and sector rotations. It filters down top potential candidates based on conviction scores generated by LLMs to feed the downstream analyst teams.

### 2. Analyst Team
Specialized domain experts dive deep into individual assets:
- **Fundamentals Analyst**: Evaluates company financials (Income Statements, Cash Flow, Balance Sheets) and performance metrics to identify intrinsic value and red flags.
- **Sentiment Analyst**: Analyzes social media and public sentiment to gauge short-term market mood.
- **News Analyst**: Monitors global news events and macroeconomic indicators, strictly interpreting facts to assess market impact.
- **Technical Analyst**: Utilizes price trends, technical indicators (MACD, RSI), and relative sector performance to detect trading patterns.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### 3. Researcher Team (Multi-Round Debate)
- Comprises **Bullish** and **Bearish** researchers who critically assess the insights provided by the Analyst Team. Through structured multi-round debates, they battle-test hypotheses to balance potential edge against inherent risks before passing findings to the Trader.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 4. Trader Agent
- The Trader acts as the execution strategist. It synthesizes the debate briefs and analyst reports to determine timing, magnitude, and the specific entry/exit logic of trades based on unified market insights.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 5. Risk Management & Portfolio Manager
- A dedicated **Risk Management** agent continuously monitors portfolio health, assessing volatility, beta correlation, and exposure limits.
- The **Portfolio Manager** is the final authority. It reviews new proposals against existing holdings—tracked via a MongoDB/Local filesystem-backed report store—acting as the ultimate gatekeeper for deploying capital.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Key Features (Suggested Addition)
- **Multi-Round Risk Debate**: Dynamic back-and-forth LLM discussions simulating real hedge-fund committee meetings.
- **Heuristic Summarization**: Intelligently compresses prompts and extracts core logic to reduce token costs by up to 50%.
- **Robust Idempotency**: Automatically saves checkpoints locally or in MongoDB; if an API timeout occurs, the pipeline pauses and restarts right where it left off.
- **Multi-Provider Support**: Seamlessly integrate with OpenAI, Anthropic, Google Gemini, OpenRouter, and local Ollama models.

## How to Use

### Installation

Clone TradingAgents:
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

Create a virtual environment in any of your favorite environment managers:
```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

Install the package and its dependencies:
```bash
pip install .
```

### Required APIs

TradingAgents supports multiple LLM providers. Set the API key for your chosen provider:

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
```

For local models, configure Ollama with `llm_provider: "ollama"` in your config.

Alternatively, copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

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

### CLI Commands

| Command | Description |
|---------|-------------|
| `analyze` | Interactive per-ticker multi-agent analysis (select analysts, LLM, date) |
| `scan` | Run the 3-phase macro scanner (geopolitical → sector → synthesis) |
| `pipeline` | Full pipeline: macro scan JSON → filter by conviction → per-ticker deep dive |
| `portfolio` | Run the Portfolio Manager workflow (requires portfolio ID + scan JSON) |
| `check-portfolio` | Review current holdings only — no new candidates |
| `auto` | End-to-end: scan → pipeline → portfolio manager (one command) |

**Examples:**

```bash
# Per-ticker analysis (interactive prompts for ticker, date, LLM, analysts)
python -m cli.main analyze

# Run macro scanner for a specific date
python -m cli.main scan --date 2026-03-21

# Run the full pipeline (scan → filter → per-ticker analysis)
python -m cli.main pipeline

# Run portfolio manager with a specific portfolio and scan results
python -m cli.main portfolio

# Review current holdings without new candidates
python -m cli.main check-portfolio --portfolio-id main_portfolio --date 2026-03-21

# Full autonomous mode: scan → pipeline → portfolio
python -m cli.main auto --portfolio-id main_portfolio --date 2026-03-21
```

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all unit tests (integration and e2e excluded by default)
python -m pytest tests/ -v

# Run only portfolio tests
python -m pytest tests/portfolio/ -v

# Run a specific test file
python -m pytest tests/portfolio/test_models.py -v

# Run tests with coverage (requires pytest-cov)
python -m pytest tests/ --cov=tradingagents --cov-report=term-missing
```

> **Note:** Integration tests that require network access or database connections
> auto-skip when the relevant environment variables (`SUPABASE_CONNECTION_STRING`,
> `FINNHUB_API_KEY`, etc.) are not set.

## TradingAgents Package

### Implementation Details

We built TradingAgents with LangGraph to ensure flexibility and modularity. The framework supports multiple LLM providers: OpenAI, Google, Anthropic, xAI, OpenRouter, and Ollama.

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
config["llm_provider"] = "openai"        # openai, google, anthropic, xai, openrouter, ollama
config["deep_think_llm"] = "gpt-5.2"     # Model for complex reasoning
config["quick_think_llm"] = "gpt-5-mini" # Model for quick tasks
config["mid_think_llm"] = "gpt-5"        # Balanced analysis tier (used by News/Fundamentals analysts)
config["llm_timeout"] = 180              # Global timeout for OpenAI-compatible model calls
config["mid_think_fallback_llm"] = "gpt-5-mini"  # Optional fallback if the primary model is blocked or rate-limited
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

See `tradingagents/default_config.py` for all configuration options.

Notes:
- The `News Analyst` and `Fundamentals Analyst` use the `mid_think` tier by default. The news path was moved off `quick_think` to improve source attribution reliability under stricter provenance validation.
- For OpenAI-compatible providers, the runtime now uses bounded request timeouts plus per-tier fallback models. Same-model retries happen in the client layer; model substitution happens in the engine layer.

## Contributing

We welcome contributions from the community! Whether it's fixing a bug, improving documentation, or suggesting a new feature, your input helps make this project better. If you are interested in this line of research, please consider joining our open-source financial AI research community [Tauric Research](https://tauric.ai/).

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
