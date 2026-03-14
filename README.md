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
  <a href="./README_ko.md">한국어</a> |
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=zh">中文</a>
</div>

---

# TradingAgents: Multi-Agents LLM Financial Trading Framework

## News
- [2026-03] **KIS Broker Integration** — Real-time trade execution via Korea Investment & Securities (한국투자증권) API. Supports both paper trading (모의투자) and real trading (실투자) with multi-layer safety guards.
- [2026-03] **Investment Persona System** — Trade like Warren Buffett, Ray Dalio, or Peter Lynch. Persona-specific strategies are injected into Trader, Research Manager, and Risk Manager agents.
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

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🎭 [Personas](#investment-personas) | 📈 [Broker Execution](#broker-execution-kis) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

## TradingAgents Framework

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents: from fundamental analysts, sentiment experts, and technical analysts, to trader, risk management team, the platform collaboratively evaluates market conditions and informs trading decisions. Moreover, these agents engage in dynamic discussions to pinpoint the optimal strategy.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

Our framework decomposes complex trading tasks into specialized roles. This ensures the system achieves a robust, scalable approach to market analysis and decision-making.

### Analyst Team
- Fundamentals Analyst: Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags. For Korean-listed companies, it also leverages [OpenDART](https://opendart.fss.or.kr/) data including official financial statements and regulatory disclosures.
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

Install dependencies:
```bash
pip install -r requirements.txt
```

### Required APIs

TradingAgents supports multiple LLM providers. Set the API key for your chosen provider:

```bash
# LLM Providers (set the one you use)
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export OPENROUTER_API_KEY=...      # OpenRouter

# Data Providers
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage (alternative to yfinance)
export OPENDART_API_KEY=...        # OpenDART (Korean DART disclosures)

# KIS Broker (한국투자증권) — only needed for trade execution
export KIS_APP_KEY=...             # KIS Open API app key
export KIS_APP_SECRET=...          # KIS Open API app secret
export KIS_ACCOUNT_NO=...          # Account number (format: XXXXXXXX-XX)
```

For local models, configure Ollama with `llm_provider: "ollama"` in your config.

Alternatively, copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

### CLI Usage

You can also try out the CLI directly by running:
```bash
python -m cli.main
```
The CLI guides you through a 9-step interactive setup: ticker, date, analysts, LLM provider & models, research depth, investment persona, and broker execution mode.

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

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, personas, and more:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # openai, google, anthropic, xai, openrouter, ollama
config["deep_think_llm"] = "gpt-5.2"     # Model for complex reasoning
config["quick_think_llm"] = "gpt-5-mini" # Model for quick tasks
config["max_debate_rounds"] = 2

# Apply an investment persona (optional)
config["persona"] = "warren_buffett"     # None, "warren_buffett", "ray_dalio", "peter_lynch"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

To enable live trade execution with KIS broker:

```python
config["broker"] = {
    "enabled": True,
    "provider": "kis",
    "mode": "paper",                 # "paper" (모의투자) or "real" (실투자)
    "default_position_pct": 0.05,    # 5% of portfolio per trade
}

ta = TradingAgentsGraph(debug=True, config=config)
final_state, decision = ta.propagate("005930", "2026-03-15")
print(decision)
print(final_state.get("execution_result", ""))  # Order execution result
```

See `tradingagents/default_config.py` for all configuration options.

### Korean Market Support (OpenDART)

TradingAgents supports Korean-listed companies through the [OpenDART API](https://opendart.fss.or.kr/), which provides official financial statements and regulatory disclosures from Korea's DART (Data Analysis, Retrieval and Transfer) system.

To enable Korean market support:

1. Get an API key from [OpenDART](https://opendart.fss.or.kr/)
2. Set the environment variable:
   ```bash
   export OPENDART_API_KEY=your_api_key_here
   ```
3. Use 6-digit Korean stock ticker codes (e.g., `005930` for Samsung Electronics):
   ```python
   _, decision = ta.propagate("005930", "2026-03-08")
   ```

The Fundamentals Analyst will automatically use `get_dart_financials` and `get_dart_disclosures` tools when analyzing Korean stocks, retrieving:
- **Financial Statements**: Revenue, operating profit, net income, and OPM from quarterly/annual DART filings
- **Disclosures**: Recent regulatory filings, earnings reports, and corporate actions from the last 30 days

### Investment Personas

TradingAgents supports investment personas that shape how the Trader, Research Manager, and Risk Manager approach their decisions. Analysts remain objective and unaffected by personas.

| Persona | Strategy | Key Principles |
|---------|----------|----------------|
| **Warren Buffett** | Value investing | Long-term holding, margin of safety, intrinsic value, moat analysis |
| **Ray Dalio** | Systematic macro | Diversified ETF allocation, rebalancing, macro-driven decisions |
| **Peter Lynch** | Growth investing | PEG ratio focus, invest in what you know, growth at reasonable price |

```python
config["persona"] = "warren_buffett"  # or "ray_dalio", "peter_lynch", None (default)
```

In CLI mode, the persona selection appears as Step 8 in the interactive wizard.

To add a custom persona, add an entry to the `PERSONAS` dict in `tradingagents/agents/personas.py` with prompt fragments for `"trader"`, `"research_manager"`, and `"risk_manager"` roles.

### Broker Execution (KIS)

TradingAgents can execute real trades through the [Korea Investment & Securities (한국투자증권)](https://apiportal.koreainvestment.com/) REST API. When enabled, an Executor node is added to the graph after the Risk Judge, automatically placing orders based on the final trading decision.

#### Setup

1. Register for a KIS Open API account at [KIS Developers](https://apiportal.koreainvestment.com/)
2. Create an app to get your APP_KEY and APP_SECRET
3. Set environment variables:
   ```bash
   export KIS_APP_KEY=your_app_key
   export KIS_APP_SECRET=your_app_secret
   export KIS_ACCOUNT_NO=12345678-01    # Format: XXXXXXXX-XX
   ```

#### Trading Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **Paper** (`"paper"`) | Simulated trading via KIS virtual trading server | Testing, development, strategy validation |
| **Real** (`"real"`) | Live trading with real money | Production use (requires explicit opt-in) |

#### Safety Guards

Multiple layers of protection are built into the execution engine:

| Guard | Default | Description |
|-------|---------|-------------|
| Paper trading default | `mode: "paper"` | Real trading requires explicit opt-in |
| Double confirmation | `require_confirmation: True` | CLI prompts twice before enabling real trades |
| Position limit | `max_position_pct: 10%` | Maximum portfolio weight per single stock |
| Order amount limit | `max_order_amount: 5,000,000 KRW` | Maximum amount per single order |
| Daily loss limit | `daily_loss_limit: -500,000 KRW` | Stops trading when daily loss exceeds limit |
| Market hours | `enforce_market_hours: True` | Orders blocked outside KRX hours (09:00-15:30 KST) |

#### Configuration

```python
config["broker"] = {
    "enabled": True,
    "provider": "kis",
    "mode": "paper",                     # "paper" or "real"
    "default_order_type": "market",      # "market" or "limit"
    "default_position_pct": 0.05,        # 5% of portfolio per trade
    "safety": {
        "max_position_pct": 0.10,
        "max_order_amount": 5_000_000,
        "daily_loss_limit": -500_000,
        "enforce_market_hours": True,
        "require_confirmation": True,
    },
}
```

#### Architecture

The broker system uses an abstract `BaseBroker` interface, making it extensible to other Korean brokers (Kiwoom, eBest, etc.) in the future:

```
ExecutionEngine (safety + orchestration)
  └── BaseBroker (abstract interface)
        └── KISBroker (KIS REST API implementation)
              └── KISClient (HTTP client + token management + rate limiting)
```

When the broker is enabled, the Trader agent also receives portfolio context (current holdings, cash balance, unrealized P&L) to make more informed decisions.

### All Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `llm_provider` | `"openai"` | LLM provider: openai, google, anthropic, xai, openrouter, ollama |
| `deep_think_llm` | `"gpt-5.2"` | Model for complex reasoning tasks |
| `quick_think_llm` | `"gpt-5-mini"` | Model for quick analysis tasks |
| `backend_url` | `"https://api.openai.com/v1"` | API endpoint URL |
| `max_debate_rounds` | `1` | Bull/Bear debate rounds |
| `max_risk_discuss_rounds` | `1` | Risk management discussion rounds |
| `data_vendors` | `{"core_stock_apis": "yfinance", ...}` | Category-level data vendor selection |
| `persona` | `None` | Investment persona |
| `broker.enabled` | `False` | Enable trade execution |
| `broker.mode` | `"paper"` | Paper or real trading |
| `google_thinking_level` | `None` | Gemini thinking config: "high", "minimal" |
| `openai_reasoning_effort` | `None` | OpenAI reasoning effort: "low", "medium", "high" |

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
