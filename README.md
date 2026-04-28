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
- [2026-04] **Auto-Trading Bot** added — full execution layer on top of TradingAgents: broker adapter (Alpaca + mock), SQLite portfolio state, risk gate, APScheduler automation, and Streamlit dashboard. See [Auto-Trading Bot](#auto-trading-bot) below.
- [2026-03] **TradingAgents v0.2.3** released with multi-language support, GPT-5.4 family models, unified model catalog, backtesting date fidelity, and proxy support.
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
config["deep_think_llm"] = "gpt-5.4"     # Model for complex reasoning
config["quick_think_llm"] = "gpt-5.4-mini" # Model for quick tasks
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

See `tradingagents/default_config.py` for all configuration options.

---

## Auto-Trading Bot

> **Disclaimer:** This bot is designed for research and paper-trading purposes. Use real-money trading at your own risk. Start with `TRADINGBOT_BROKER=mock` and graduate to Alpaca paper trading before touching live capital. This is not financial advice.

The auto-trading bot extends TradingAgents from a pure analysis tool into a full execution system. It adds four layers on top of the existing agent pipeline:

```
TradingAgents Analysis Pipeline  (existing)
          │
          ▼  BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL
   ┌──────────────┐
   │  SignalMapper │  translates 5-tier signal → order qty + side
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │   RiskGate   │  hard limits: exposure cap, circuit breaker,
   └──────┬───────┘  cash reserve, position concentration
          │ approved?
          ▼
   ┌──────────────┐
   │ BrokerAdapter│  Alpaca (paper/live) or MockBroker
   └──────┬───────┘
          │ filled order
          ▼
   ┌──────────────────┐
   │ PortfolioManager │  SQLite: trades, snapshots, closed P&L
   └──────┬───────────┘
          │ realised P&L on SELL
          ▼
   TradingAgentsGraph.reflect_and_remember()   ← agents learn
          │
          ▼
   ┌─────────────────┐
   │   Dashboard     │  Streamlit web UI
   └─────────────────┘
```

### New File Structure

```
tradingbot/
├── config.py                  # All env-var-driven configuration
├── broker/
│   ├── base.py                # BrokerAdapter ABC + data models
│   ├── alpaca.py              # Alpaca Markets (paper & live)
│   ├── mock.py                # In-memory mock (yfinance prices)
│   └── signal_mapper.py       # 5-tier signal → OrderInstruction
├── portfolio/
│   ├── models.py              # TradeRecord, PortfolioSnapshot, PerformanceMetrics
│   ├── database.py            # SQLite: trades / snapshots / closed_positions
│   └── manager.py             # Bridges broker ↔ DB, computes Sharpe/drawdown
├── risk/
│   └── gate.py                # RiskGate — 5 hard limits, never LLM-overridable
├── scheduler/
│   ├── runner.py              # AutoTrader — full pipeline per ticker
│   └── scheduler.py           # APScheduler: pre-market / order-submit / post-market
└── dashboard/
    ├── app.py                 # Streamlit entry point
    └── components/
        ├── portfolio_view.py  # Live positions table + allocation pie
        ├── performance_view.py# Equity curve, drawdown, daily P&L, metrics
        ├── trades_view.py     # Trade history + agent reasoning + closed P&L
        ├── signals_view.py    # Run live analysis from the UI (no execution)
        └── risk_view.py       # Circuit breaker, exposure gauge, concentration

run_bot.py          # CLI entry point for the bot
run_dashboard.py    # Convenience launcher for the Streamlit dashboard
```

### Installation

Install the extra dependencies (added to `pyproject.toml`):

```bash
pip install .
# installs alpaca-py, apscheduler, streamlit, plotly alongside existing deps
```

### Configuration

All settings are driven by environment variables. Add them to your `.env` file or export them in your shell.

#### Broker

| Variable | Default | Description |
|---|---|---|
| `TRADINGBOT_BROKER` | `mock` | `mock` (no credentials) or `alpaca` |
| `ALPACA_API_KEY` | — | Required for Alpaca |
| `ALPACA_API_SECRET` | — | Required for Alpaca |
| `ALPACA_PAPER` | `true` | `true` = paper trading, `false` = live |

#### Watchlist & Position Sizing

| Variable | Default | Description |
|---|---|---|
| `TRADINGBOT_WATCHLIST` | `AAPL,MSFT,NVDA,GOOGL,AMZN` | Comma-separated tickers |
| `FULL_POSITION_PCT` | `0.05` | Cash fraction allocated on a BUY signal (5 %) |
| `PARTIAL_POSITION_PCT` | `0.03` | Cash fraction allocated on an OVERWEIGHT signal (3 %) |
| `PARTIAL_EXIT_PCT` | `0.50` | Fraction of position sold on an UNDERWEIGHT signal (50 %) |

#### Risk Limits

| Variable | Default | Description |
|---|---|---|
| `MAX_SINGLE_POSITION_PCT` | `0.10` | Max portfolio fraction in one ticker (10 %) |
| `MAX_TOTAL_EXPOSURE_PCT` | `0.80` | Max portfolio fraction invested at any time (80 %) |
| `DAILY_LOSS_LIMIT_PCT` | `-0.02` | Circuit breaker: halt buys if daily P&L < −2 % |
| `MIN_CASH_RESERVE` | `1000.0` | Minimum cash (USD) always kept available |

#### Schedule (all times in US/Eastern)

| Variable | Default | Description |
|---|---|---|
| `PRE_MARKET_TIME` | `08:00` | When to run agent analysis |
| `ORDER_SUBMISSION_TIME` | `09:35` | When to submit approved orders |
| `POST_MARKET_TIME` | `16:30` | When to snapshot portfolio and run agent reflection |

#### Storage

| Variable | Default | Description |
|---|---|---|
| `TRADINGBOT_DB_PATH` | `~/.tradingagents/tradingbot.db` | SQLite database path |

### Running the Bot

#### Option 1 — One-shot test (mock broker, no credentials needed)

```bash
# Analyse a single ticker for today and (mock) execute the trade
python run_bot.py --ticker AAPL --once

# Analyse a specific historical date
python run_bot.py --ticker NVDA --date 2024-05-10 --once

# Run the full watchlist once
python run_bot.py --once
```

#### Option 2 — Human-in-the-loop (review before each trade)

```bash
python run_bot.py --once --approval
# Prints the signal + agent summary, waits for y/n before submitting
```

#### Option 3 — Continuous scheduled mode

```bash
# Runs 3 cron jobs every weekday: pre-market analysis, order submission, post-market reflection
python run_bot.py
```

Press `Ctrl-C` to stop.

#### Option 4 — Alpaca paper trading

```bash
export TRADINGBOT_BROKER=alpaca
export ALPACA_API_KEY=your_key
export ALPACA_API_SECRET=your_secret
export ALPACA_PAPER=true

python run_bot.py --ticker AAPL --once
```

### Running the Dashboard

```bash
python run_dashboard.py
```

Or directly with Streamlit:

```bash
streamlit run tradingbot/dashboard/app.py
```

The dashboard opens at `http://localhost:8501` and contains five pages:

| Page | What it shows |
|---|---|
| **Portfolio** | Live positions table (entry price, current price, unrealised P&L), allocation pie chart, 4 KPI cards |
| **Performance** | Equity curve, drawdown chart, daily P&L bar chart, Sharpe ratio, max drawdown, win rate, profit factor |
| **Trade History** | Every executed trade (filterable by ticker/side), full agent reasoning per trade, closed-position P&L table |
| **Agent Signals** | Run a live analysis for any ticker/date from the UI — see the full multi-agent debate without executing a trade |
| **Risk Monitor** | Circuit breaker status, portfolio exposure gauge with cap markers, per-position concentration bar chart |

The sidebar also includes a **Quick Trade** panel for placing manual orders directly from the UI.

The dashboard reads from the same SQLite database as the bot, so it works whether the bot is currently running or not. Click **Refresh Data** in the sidebar to pull the latest state.

### How the Learning Loop Closes

Every time a SELL order is executed, the bot:

1. Records the closed position P&L in the database.
2. Calls `TradingAgentsGraph.reflect_and_remember(realised_pnl)`.
3. The existing Reflector agents (Bull, Bear, Trader, Research Manager, Portfolio Manager) generate lessons learned.
4. Those lessons are stored in BM25 memory and surface in future analysis runs for similar market situations.

This means the agents get better over time as they accumulate real trade outcomes — not just simulated ones.

---

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
