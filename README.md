# TradingAgents-Jev

**by NoSlack Labs**

The slow lane of a three-speed trading system: LLM agents decide what to trade,
how much risk to take and when to stand down. The fast lanes, a C++ engine and
an FPGA pipeline that never wait on a model, live in
[129BOB](https://github.com/sushant-mishra-dtu/129BOB).

This is a fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
([arXiv 2412.20138](https://arxiv.org/abs/2412.20138), Apache 2.0). It adds
[TypeSafe Jev](https://docs.typesafe.ai) typed judgments where an LLM's free
text is a poor fit, and keeps numbers, dates and counting in code.

## What this fork adds

| Addition | What it does | Where |
| --- | --- | --- |
| Screened, scored sentiment | Jev judges each news article and social post: off-topic items, repeats and posts carrying instructions aimed at an AI are dropped; the sentiment band, score and confidence are computed in code from per-item stances, and the LLM writes only the narrative | [TypeSafe Jev](#typesafe-jev-optional) |
| Debates that stop early | The bull/bear and risk debates end once a full round adds no new argument, saving one call per skipped turn | [TypeSafe Jev](#typesafe-jev-optional) |
| Claim check on the final decision | The Portfolio Manager's thesis is checked against the analyst reports; a contradicted claim turns the rating into `REVIEW` instead of a trade | [TypeSafe Jev](#typesafe-jev-optional) |
| Learning from the reports | `tradingagents learn` tests whether Jev's judgments of a backtest's reports predict outcomes better than the rating alone, on chronological holdouts | [Learning from the reports](#learning-from-the-reports-jev) |
| Browser UI | Analyze a ticker and watch each desk stream in, inspect every sentiment judgment, read saved reports and run backtests | [Browser UI](#browser-ui) |

The survey of where Jev fits, and how each fit was built and checked, is in
[docs/jev-use-cases.md](docs/jev-use-cases.md).

## Quick start

```bash
git clone https://github.com/sushant-mishra-dtu/TradingAgents-Jev.git
cd TradingAgents-Jev
uv venv --python 3.12 && source .venv/bin/activate
uv pip install ".[jev]"
cp .env.example .env      # add an LLM provider key, and TYPESAFE_API_KEY for Jev
tradingagents ui          # http://localhost:8501
```

Without `TYPESAFE_API_KEY` everything runs as upstream TradingAgents does. Set
`TRADINGAGENTS_JEV_ENABLED=false` to turn every Jev call off with the key set.

> For research only. Not financial, investment or trading advice.

---

The rest of this README is the upstream documentation, updated where the fork
changes behaviour. All credit for the underlying framework goes to its authors.

# TradingAgents: Multi-Agents LLM Financial Trading Framework

## News

<!-- news:start -->
- [2026-09] **TradingAgents v0.5.1** released with a package layout organised by what each module holds (import paths moved), optional Jev screening of social posts, GPT-6 Sol and Luna as the default models, and fixes to run isolation and SEC EDGAR statements.
- [2026-09] **TradingAgents v0.5.0** released with point-in-time integrity across every dated path, SEC EDGAR fundamentals served as filed, backtesting over a ticker and date grid, portfolio-aware runs, and current model lineups across every provider.
- [2026-08] **TradingAgents v0.4.0** released with look-ahead / point-in-time fixes across FRED macro, social sentiment, and the decision-log memory; clearer decision signals; working CLI checkpoint resume; Trader price grounding; and the GPT-5.6 and GLM-5.3 models.

Full release notes are in [CHANGELOG.md](CHANGELOG.md).

<details>
<summary>Earlier news</summary>

- [2026-07] **TradingAgents v0.3.1** released with correctness and stability fixes: Alpha Vantage look-ahead filtering, graph-router crash-safety, graph-shape-aware checkpoint resume, working crypto sentiment sources, a configurable LLM retry budget, Bedrock API-key auth, and Claude Sonnet 5 / Fable 5 support.
- [2026-06] **TradingAgents v0.3.0** released with a verified data-access contract, an expanded provider registry (NVIDIA, Kimi, Groq, Mistral, Bedrock, and any OpenAI-compatible endpoint), FRED and Polymarket data vendors, a current-generation model catalog, and a CI gate.
- [2026-05] **TradingAgents v0.2.5** released with the grounded Sentiment Analyst, GPT-5.5 etc. model coverage, Qwen/GLM/MiniMax dual-region support, `TRADINGAGENTS_*` env-var configurability with API-key auto-detection, remote Ollama support, non-US alpha benchmarks, and ticker path-traversal hardening.
- [2026-04] **TradingAgents v0.2.4** released with structured-output agents (Research Manager, Trader, Portfolio Manager), LangGraph checkpoint resume, persistent decision log, DeepSeek/Qwen/GLM/Azure provider support, Docker, and a Windows UTF-8 encoding fix.
- [2026-03] **TradingAgents v0.2.3** released with multi-language support, GPT-5.4 family models, unified model catalog, backtesting date fidelity, and proxy support.
- [2026-03] **TradingAgents v0.2.2** released with GPT-5.4/Gemini 3.1/Claude 4.6 model coverage, five-tier rating scale, OpenAI Responses API, Anthropic effort control, and cross-platform stability.
- [2026-02] **TradingAgents v0.2.0** released with multi-provider LLM support (GPT-5.x, Gemini 3.x, Claude 4.x, Grok 4.x) and improved system architecture.
- [2026-01] **Trading-R1** [Technical Report](https://arxiv.org/abs/2509.11420) released, with [Terminal](https://github.com/TauricResearch/Trading-R1) expected to land soon.

</details>
<!-- news:end -->

<div align="center">

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

> 🎉 **TradingAgents** officially released! We have received numerous inquiries about the work, and we would like to express our thanks for the enthusiasm in our community.
>
> So we decided to fully open-source the framework. Looking forward to building impactful projects with you!

## TradingAgents Framework

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents: from fundamental analysts, sentiment experts, and technical analysts, to trader, risk management team, the platform collaboratively evaluates market conditions and informs trading decisions. Moreover, these agents engage in dynamic discussions to pinpoint the optimal strategy.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

Our framework decomposes complex trading tasks into specialized roles.

### Analyst Team
- Fundamentals Analyst: Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags.
- Sentiment Analyst: Aggregates news headlines, StockTwits, and Reddit chatter into a single sentiment read to gauge short-term market mood.
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
- Composes reports from the analysts and researchers to make informed trading decisions, determining the timing and magnitude of trades.

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

Clone TradingAgents-Jev:
```bash
git clone https://github.com/sushant-mishra-dtu/TradingAgents-Jev.git
cd TradingAgents-Jev
```

Create a virtual environment in any of your favorite environment managers:
```bash
conda create -n tradingagents python=3.12
conda activate tradingagents
```

Or with [uv](https://docs.astral.sh/uv/):
```bash
uv venv --python 3.12
source .venv/bin/activate
```

Install the package and its dependencies (`uv pip install .` with uv):
```bash
pip install .
```

### Docker

Alternatively, run with Docker:
```bash
cp .env.example .env  # add your API keys
docker compose run --rm tradingagents
```

After updating the repository, rebuild the image with `docker compose build`.

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
export DASHSCOPE_API_KEY=...       # Qwen — International (dashscope-intl.aliyuncs.com)
export DASHSCOPE_CN_API_KEY=...    # Qwen — China (dashscope.aliyuncs.com)
export ZHIPU_API_KEY=...           # GLM via Z.AI (international)
export ZHIPU_CN_API_KEY=...        # GLM via BigModel (China, open.bigmodel.cn)
export MINIMAX_API_KEY=...         # MiniMax — Global (api.minimax.io)
export MINIMAX_CN_API_KEY=...      # MiniMax — China (api.minimaxi.com)
export OPENROUTER_API_KEY=...      # OpenRouter
export MISTRAL_API_KEY=...         # Mistral
export MOONSHOT_API_KEY=...        # Kimi (Moonshot)
export GROQ_API_KEY=...            # Groq
export NVIDIA_API_KEY=...          # NVIDIA NIM
export FRED_API_KEY=...            # FRED macro data (free, optional)
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
export TYPESAFE_API_KEY=...        # Jev social-post screening (optional)
```

For Azure OpenAI, copy `.env.enterprise.example` to `.env.enterprise` and fill in your credentials.

For AWS Bedrock, install the extra with `pip install ".[bedrock]"`, set `llm_provider: "bedrock"`, configure AWS credentials (environment variables, `~/.aws/credentials`, or an IAM role) and `AWS_DEFAULT_REGION`, and use a Bedrock model ID, e.g. `us.anthropic.claude-opus-4-8-v1:0`.

For NVIDIA NIM, set `llm_provider: "nvidia"`. The picker lists Nemotron 3 Super 120B (`nvidia/nemotron-3-super-120b-a12b`, 1M context, tool calling) for both the quick and deep model; pick "Custom model ID" for any other NIM model. The free build.nvidia.com endpoints run on trial credits and are meant for testing and evaluation.

Shared and trial endpoints such as NVIDIA NIM sometimes return bursts of server errors mid-run. For OpenAI and every OpenAI-compatible provider (all of the above except Anthropic, Google, Azure and Bedrock), a call that hits a 5xx, a dropped connection or a rate limit is retried after 10, 20, 40, 60 and 60 seconds, on top of the SDK's own quick retries, before the run fails. Each retry is logged.

For local models, configure Ollama with `llm_provider: "ollama"`. The default endpoint is `http://localhost:11434/v1`; set `OLLAMA_BASE_URL` to point at a remote `ollama-serve`. Pull models with `ollama pull <name>`, and pick "Custom model ID" in the CLI for any model not listed by default.

For any other OpenAI-compatible server (vLLM, LM Studio, llama.cpp, or a custom relay), use `llm_provider: "openai_compatible"` and set the endpoint via `backend_url` (or `TRADINGAGENTS_LLM_BACKEND_URL`), e.g. `http://localhost:8000/v1` for vLLM or `http://localhost:1234/v1` for LM Studio. The model is whatever your server serves. No key is needed for local servers; set `OPENAI_COMPATIBLE_API_KEY` when the endpoint requires one.

With `TYPESAFE_API_KEY` set, the Sentiment Analyst screens StockTwits and Reddit posts with TypeSafe's Jev before reading them. Posts that are not about the company are dropped, and each source opens with a count of the remaining posts by stance: bullish, bearish, neutral, or unclear. Without the key, posts pass through unscreened. `jev-latest` moves with new releases; set `TYPESAFE_DEFAULT_MODEL` to a versioned ID such as `jev-1.13.0` to hold it fixed across runs.

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
You will see a screen where you can select your desired tickers, analysis date, LLM provider, research depth, and more. Your previous run's answers come back as the defaults, so pressing Enter accepts them. The `TRADINGAGENTS_*` variables in `.env` still skip their step entirely.

### Browser UI

The same workflow in a browser, plus a history of past reports and a backtest dashboard. It needs nothing beyond the base install:
```bash
tradingagents ui       # serves http://localhost:8501 and opens the Analyze page
tradingagents ui --port 8600 --no-browser
```
- **Analyze** — pick a ticker, date, analysts and an optional portfolio file, then watch each desk of the pipeline, the metrics, tool calls and report sections as the run streams in. The portfolio manager's rating shows at the end, and the full report is saved under `results_dir/reports`. The ticker box searches by symbol or company name, so "reliance industries" offers `RELIANCE.NS` and "tencent" offers `0700.HK`; a provider retry shows in the run's activity log instead of the run looking stalled.
- **Company** — one stock's fundamentals laid out like a stock screener: key ratios, a price chart with 50- and 200-day averages and volume, quarterly results, profit and loss with a TTM column, balance sheet, cash flows, working-capital ratios, compounded growth, and pros and cons from fixed rules (no LLM). Indian companies show figures in ₹ crores with Indian digit grouping, and banks get a lender's layout. The figures come live from Yahoo Finance, usually about four years and five quarters, and only what Yahoo has is shown. Because they are today's figures rather than point-in-time ones, no analysis or backtest reads them. **Analyze with agents** opens the Analyze page with the ticker filled in.
- **Screens** — filter every NSE stock on its fundamentals, shareholding and price with conditions such as `Market Capitalization > 500 AND ROCE > 20`; see [Stock screener](#stock-screener-india) below.
- **Sentiment** — with Jev on, every news article and social post the Sentiment Analyst judged: its stance, event type, relevance and whether it was kept, or dropped as a duplicate, off-topic or an injected instruction. Open it from a live run or from a saved report.
- **Reports** — read any saved report by section, and browse the decision log with each call's alpha, decision and reflection.
- **Backtest** — start a grid sweep (the tickers box completes each comma-separated entry the same way), follow the cell being run, stop it between cells, then compare mean alpha and hit rate by rating.

Ticker search asks Yahoo Finance and falls back to a built-in list of well-known symbols when Yahoo is unreachable or rate-limited. Model settings live in the sidebar of the Analyze page and share the CLI's remembered answers and `.env` overrides. Runs continue in the background, so reloading the page does not stop them. The server binds to `127.0.0.1`; pass `--host 0.0.0.0` only on a network you trust, since the page starts paid LLM runs. `http://localhost:8501/` itself is an overview page, and the light/dark theme follows your system unless you pick one.

### TypeSafe Jev (optional)

With `pip install ".[jev]"` and `TYPESAFE_API_KEY` set, the Sentiment Analyst first judges each news article and social post with [TypeSafe Jev](https://docs.typesafe.ai). It drops items about other companies, repeats, and posts carrying instructions aimed at an AI system, then computes the sentiment band, score and confidence from per-item stances; the LLM writes only the narrative. This takes the place of the post screening above, so posts are not sent to Jev twice; with the key but without the extra, only the post screening runs. The bull/bear and risk debates end early once a full round adds no new argument (never before round 2 or past the configured rounds, so this applies from three rounds up), and the Research Manager gets Jev's read of whose case is better supported as a hint.

At the end of the run, the Portfolio Manager's Investment Thesis is checked against the analyst reports, which the Portfolio Manager never reads itself. Jev judges which claims are checkable facts and whether each report section supports or contradicts them; figures are matched in code, and a claim that could only be settled by comparing numbers is marked unverified rather than judged. The result is appended to the decision, and a contradicted claim, or a thesis whose claims are mostly not found in the reports, turns the rating into `REVIEW` instead of a trade. Set `TRADINGAGENTS_JEV_CLAIM_CHECK=false` to turn off the claim check alone, or `TRADINGAGENTS_JEV_ENABLED=false` to turn off every Jev call, the post screening included.

After a backtest, `tradingagents learn <run id>` tests whether Jev's judgments of the reports predict outcomes better than the rating alone; see [Learning from the reports](#learning-from-the-reports-jev). Details: [docs/jev-use-cases.md](docs/jev-use-cases.md).

### Markets and tickers

TradingAgents works with any market Yahoo Finance covers, using the exchange-suffixed ticker. Company identity and the alpha benchmark resolve automatically per market.

- US: `AAPL`, `SPY`
- Hong Kong: `0700.HK` · Tokyo: `7203.T` · London: `AZN.L`
- India: `RELIANCE.NS`, `.BO` · Canada: `.TO` · Australia: `.AX`
- China A-shares: Shanghai `.SS`, Shenzhen `.SZ` (e.g. `600519.SS` for Kweichow Moutai)
- Crypto: `BTC-USD`, `ETH-USD`

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

We built TradingAgents with LangGraph to ensure flexibility and modularity. The framework supports multiple LLM providers: OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen (Alibaba DashScope, international and China endpoints), GLM (Zhipu), MiniMax (global + China), OpenRouter, Ollama for local models, and Azure OpenAI for enterprise.

### Python Usage

To use TradingAgents inside your code, you can import the `tradingagents` module and initialize a `TradingAgentsGraph()` object. The `.propagate()` function will return a decision. You can run `main.py`, here's also a quick example:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
_, decision = ta.propagate("NVDA", "2026-09-01")
print(decision)
```

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, etc.

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # e.g. openai, google, anthropic, deepseek, groq, ollama; openai_compatible covers any OpenAI-compatible endpoint (vLLM, LM Studio, llama.cpp, ...)
config["deep_think_llm"] = "gpt-6-sol"    # Model for complex reasoning
config["quick_think_llm"] = "gpt-6-luna"   # Model for quick tasks
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-09-01")
print(decision)
```

See `tradingagents/default_config.py` for all configuration options.

### India data (NSE archives and filings)

`tradingagents india ...` keeps a local SQLite database of Indian listed companies (`TRADINGAGENTS_INDIA_DB`, default `~/.tradingagents/india/india.db`; raw downloads cached under `<cache>/india/raw`). The Company page uses it for `.NS`/`.BO` symbols and falls back to Yahoo Finance section by section.

```bash
tradingagents india sync-securities                 # NSE equity list + index industries
tradingagents india sync-prices --from 2016-01-01   # bhavcopies + delivery, one-time backfill
tradingagents india sync-actions --from 2016-01-01  # splits, bonuses, rights, dividends, shares issued
tradingagents india import ~/Downloads/xbrl         # results / shareholding XBRL you saved
tradingagents india status
tradingagents india sync-all                        # the nightly run (schedule it yourself)
tradingagents india reparse-actions                 # re-read stored corporate actions after a parser fix
```

Sources and their terms (checked 2026-10-05):
- **archives.nseindia.com** (equity list, index lists, bhavcopies with ISIN from 2016, MTO deliveries and daily PR files from 2010) is fetched at most once a second with an honest User-Agent. NSE's Terms of Use prohibit "systematic or automated data collection"; running these syncs is your decision, for personal use.
- **NSE's JSON APIs and nsearchives.nseindia.com** (where results and shareholding XBRL live) answer only browsers, and **BSE** refuses non-browser clients. They are not fetched. Save filings from NSE's (or BSE's) filing pages and import them; drop them in `<cache>/india/inbox` for `sync-results`, `sync-shareholding` and `sync-all`.

Every financial and shareholding value keeps its `filed_at`; restatements are kept as separate rows, and `store.get_financials(isin, as_of=...)` sees only what was public by then.

### Stock screener (India)

The **Screens** page and `tradingagents screen ...` filter every stock in the India database on about 100 metrics. Screens read a precomputed snapshot, so build one once the database has prices:

```bash
tradingagents india build-snapshot                      # the live snapshot (also rebuilt by india sync-all)
tradingagents india build-snapshot --as-of 2025-10-06   # a historical one, kept beside it
tradingagents screen run "Market Capitalization > 500 AND Return on capital employed > 20"
tradingagents screen run "Return over 1 year > 20" --as-of 2025-10-06 --limit 50 --sort return_1y
tradingagents screen list                               # your saved screens and the presets
tradingagents screen metrics growth                     # the metrics whose names match "growth"
```

**Query syntax.** A condition compares metrics, numbers and arithmetic: `ROCE > 20`, `Current price > 200 DMA`, `Net profit / Sales * 100 > 10`. Comparisons are `> < >= <= = !=`; join conditions with `AND`, `OR`, `NOT` and brackets, or write one per line: a new line is an AND that binds loosest, so each line stands on its own (`ROCE > 20` then `ROE > 15 OR P/E < 10` on the next line means ROCE > 20 AND (ROE > 15 OR P/E < 10)). Text metrics (Name, NSE symbol, Industry, also called Sector) take quoted values, `Industry = 'Capital Goods'` or `Industry IN ('Power', 'Utilities')`, ignoring case. Metric names hold spaces and match their aliases case-insensitively (`Return on capital employed`, `ROCE`, `ROCE %`). Numbers may be written `1,000`, `1,00,000`, `1e3` or `20%`. A query is at most 4,000 characters and 40 levels deep, and runs for at most 2 seconds. Errors say where, by line and column, and suggest the metric you meant: `Unknown metric 'Retrun on equity' at col 1 — did you mean 'Return on equity'?`.

**Units.** Amounts are in Rs. crores (`Market Capitalization > 500` is Rs 500 Cr), per-share figures in rupees, percentages in % (`ROE > 15`), changes in holdings in percentage points, and multiples (P/E, debt to equity) as plain numbers. Each metric's unit is listed on the page and by `screen metrics`.

**Missing data never passes.** A comparison with a value the database lacks is unknown, and stays unknown under `NOT`, so the stock is left out; only a branch of an `OR` that is true for it can let it in. The page and the CLI say how many stocks were left out for missing data. Banks and NBFCs have no ROCE, margins, debt to equity or working-capital figures, so they drop out wherever those are used. Division by zero gives a blank, not an error.

**What the figures are.** "TTM" is the latest four quarters summed when the newest quarter is after the newest fiscal year, else that year; "last year" is the newest fiscal year filed; balance-sheet figures are the newest year-end balance sheet's. Prices are adjusted for splits, bonuses and rights, not dividends, and a stock with no close in the 15 days before the snapshot has no price. Market capitalisation is the last close times the shares outstanding: NSE's own issued-share count from its daily PR file when the database has it, else the latest shareholding pattern's total, else equity capital over face value, each multiplied by any split or bonus since its date. Dividend yield is the past year's dividends per share over the price, 0 when none was paid, blank if the corporate-actions sync does not cover the year. Every formula is the Company page's own (`dataflows/formulas.py`), and the Company page lists every metric in its **All metrics** section, so the two always agree.

**Snapshots.** `metrics_snapshot` in the India database holds a row per stock and a column per metric, keyed by `as_of_date` (`live`, or a date). A historical snapshot reads the database point in time: filings filed by its date, prices up to it, and actions known by then; its universe is the stocks that traded in the 15 days before it, so stocks delisted since stay in. The default universe is listed EQ-series stocks (`screener_universe`: `eq`, `listed`, `all`, or `--universe RELIANCE,TCS`). Pick a historical snapshot on the page, or pass `--as-of`. The fundamentals screens need results and shareholding filings imported (`tradingagents india import`); with prices only, the price, return, moving-average, market-cap and dividend metrics work and the rest are blank.

**Custom ratios.** Define `Name = expression` over catalog metrics, such as `Earnings to price = Net profit / Market Capitalization`, then use the name in any query. A ratio's name may not be a catalog name or alias, ratios may use other ratios but never in a circle or more than 8 deep, and each is compiled into the query rather than stored. Saved screens and ratios live in `~/.tradingagents/screener/screens.db` (`TRADINGAGENTS_SCREENER_DB`).

**Presets.** Nine read-only starting points, written for this project: debt-free compounders, high ROCE at a reasonable P/E, consistent five-year growers, Piotroski 8 or 9, promoters raising their stake, low price to book with positive free cash flow, near the 52-week high and still growing, dividend yield with low payout risk, and large caps in an uptrend. Duplicate one to edit it. They are not investment advice.

**Analyze with agents.** Tick up to 10 result rows and confirm to queue a full analysis of each. They run one after another, never at once, and each costs LLM calls on the provider in the Analyze page's settings. The queue shows each run's progress, links to it, and can take a run off or stop it.

### Fundamentals as filed

US company statements can come from SEC EDGAR, which records the date every figure was filed. A run dated in the past then reads the statements exactly as they stood that day: a fiscal year that has ended but has not been filed yet is not served, and a figure restated later still reads as first reported. Apple's 2008 total assets were filed as $39.6B and restated to $36.2B in 2010, so a run dated in between reads $39.6B.

EDGAR needs no account or API key. Add the vendor to the chain:

```python
config["data_vendors"]["fundamental_data"] = "sec_edgar,yfinance"
```

SEC asks callers to identify themselves and refuses requests that carry no contact address, so a default one is sent. Set your own so SEC can reach you rather than the project:

```bash
SEC_EDGAR_USER_AGENT="Your Name your@email.com"
```

It covers companies that file with the SEC, including foreign companies listed in the US. Anything else, such as Hong Kong or A-share listings, falls through to the next vendor in the chain. EDGAR's machine-readable filings begin in 2009, and a fourth quarter is reported as unavailable rather than derived, because filers publish it only inside the annual figure.

### Current holdings

By default the agents do not know what you hold, so their guidance is written for a reader who applies it to their own position. Pass a portfolio to have the trader, the risk analysts and the portfolio manager work against your actual book.

```python
from tradingagents.portfolio import PortfolioContext

portfolio = PortfolioContext.model_validate({
    "cash": 25000.0,
    "currency": "USD",
    "positions": [{"ticker": "NVDA", "quantity": 120, "average_price": 150.0}],
})
_, decision = ta.propagate("NVDA", "2026-09-01", portfolio=portfolio)
```

The CLI takes the same content as a JSON file: `tradingagents --portfolio my_book.json`.

An empty `positions` list means a flat book, which is different from passing nothing. A run without a portfolio is never treated as flat.

## Persistence and Recovery

TradingAgents persists two kinds of state across runs.

### Decision log

The decision log is always on. Each completed run appends its decision to `~/.tradingagents/memory/trading_memory.md`. On the next run for the same ticker, TradingAgents fetches the realised return (raw, and alpha against the instrument's regional benchmark), generates a one-paragraph reflection, and injects the most recent same-ticker decisions plus recent cross-ticker lessons into the Portfolio Manager prompt, so each analysis carries forward what worked and what didn't.

Override the path with `TRADINGAGENTS_MEMORY_LOG_PATH`.

### Checkpoint resume

Checkpoint resume is on by default; turn it off with `--no-checkpoint`, `TRADINGAGENTS_CHECKPOINT_ENABLED=false`, or the toggle in the web UI. When enabled, LangGraph saves state after each node so a crashed or interrupted run resumes from the last successful step instead of starting over. The run view says whether it resumed a saved run or started fresh. Checkpoints are cleared automatically on successful completion.

Per-ticker SQLite databases live at `~/.tradingagents/cache/checkpoints/<TICKER>.db` (override the base with `TRADINGAGENTS_CACHE_DIR`). Use `--clear-checkpoints` to reset all of them before a run.

```bash
tradingagents --no-checkpoint        # disable for this run
tradingagents --clear-checkpoints    # reset before running
```

```python
config = DEFAULT_CONFIG.copy()
config["checkpoint_enabled"] = False  # opt out
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2026-09-01")
```

## Evaluating decisions over time

One run gives one decision, which cannot tell you whether the system decides well. `run_backtest` runs the same pipeline over a grid of tickers and dates, writes to a decision log of its own, and scores the decisions whose holding window has since traded.

```python
from tradingagents.backtest import iter_grid, run_backtest, summarize

dates = iter_grid("2026-06-01", "2026-08-01", every_n_days=7)
result = run_backtest(["NVDA", "AAPL"], dates, config, selected_analysts=["market", "news"])
print(summarize(result).render())
```

From the CLI:

```bash
tradingagents backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01 --every 7
```

Each cell is scored on realized alpha against the instrument's regional benchmark, grouped by rating. Your own decision log is never written to, and re-running the same grid with `run_id=result.run_id` skips the cells that already ran, so an interrupted sweep continues where it stopped.

### Learning from the reports (Jev)

A backtest also keeps every cell's reports, so they can be tested against the outcomes. With the `jev` extra and `TYPESAFE_API_KEY` set:

```bash
tradingagents backtest NVDA,AAPL,MSFT,AMD --start 2026-03-02 --end 2026-08-31 --every 7 --run-id sweep1
tradingagents learn sweep1
```

`learn` asks Jev 14 fixed questions about each settled decision's reports, debates and final decision, such as the price trend, how stretched the valuation is, and which side won the bull/bear debate. It turns the answers into numeric columns and fits a small logistic model of whether the decision beat its benchmark. It holds out the latest dates, and then reports three things:

- whether the model predicts better than the rating alone on the held-out dates;
- which questions help;
- which decisions it predicted worst.

Every split is chronological, and a decision trains a model only if its outcome was already known. The answers are cached, so running `learn` again, or adding a question, asks Jev only what it has not answered. A feature table, `report_features.csv`, is written to the run folder.

This needs at least 40 settled decisions over 6 analysis dates, and many more before a result means much. Nothing in an analysis run uses the model yet. Details, and a live check of the questions: [Fit 5 as built](docs/jev-use-cases.md#fit-5-as-built).

## Reproducibility

TradingAgents is LLM-driven, so two runs of the same ticker and date can differ. This is expected for a research tool built on language models, not a defect. The variation comes from a few distinct sources, and it helps to separate them.

Language model sampling is non-deterministic. Even at a fixed temperature, providers do not guarantee byte-identical output across calls, and reasoning models (the default GPT-6 family, and any thinking-mode model) vary the most because their internal reasoning is itself sampled.

Live data moves. News, StockTwits, and Reddit return different content as time passes, so a run today sees different inputs than a run last week even for the same historical trade date. Pin the analysis date to hold the price and indicator window fixed, but the social and news sources still reflect "now".

To reduce variation you can lower the sampling temperature. Set `temperature` in your config (or `TRADINGAGENTS_TEMPERATURE` in `.env`); lower values make models that honor it more repeatable. The current curated models are reasoning-first and largely ignore temperature, so for tighter reproducibility name a non-reasoning model in your config, or in `TRADINGAGENTS_DEEP_THINK_LLM` and `TRADINGAGENTS_QUICK_THINK_LLM`. Any model ID your provider serves is accepted, whether or not the picker lists it.

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["temperature"] = 0.0
# Reasoning models ignore temperature. For tighter reproducibility, name a
# non-reasoning model in deep_think_llm / quick_think_llm.
```

What does not vary anymore: the analyzed company identity is resolved deterministically from the ticker before any agent runs, and the market analyst grounds exact price and indicator claims in a verified data snapshot. Earlier reports of "different companies" or fabricated price levels across runs are addressed by these two mechanisms.

Backtest results are not guaranteed to match any published figure. Returns depend on the model, the temperature, the date range, data quality, and the sampling above. Treat the framework as a research scaffold for studying multi-agent analysis, not as a strategy with a fixed, replicable return.

## Contributing

Contributions are welcome: bug fixes, documentation, and feature ideas; past contributions are credited per release in [`CHANGELOG.md`](CHANGELOG.md).

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
