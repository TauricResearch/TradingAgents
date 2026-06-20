# TradingAgents — Project Context for Claude Code Sessions

## What this repo is

TradingAgents is an open-source multi-agent LLM framework for investment research
(upstream: https://github.com/TauricResearch/TradingAgents). It runs a pipeline of
specialised AI agents — analysts, a bull/bear debate, a risk panel, a trader, and a
portfolio manager — against a given ticker and date, and produces a structured
investment decision with supporting reports.

This fork is being adapted as a **personal research co-pilot** for a retail investor's
satellite portfolio. All changes in this repo exist to serve that specific use case.
The upstream framework is not being modified for general-purpose use.

---

## The investor context — read this before touching any prompt or schema

Every decision this tool produces is for a **retail investor with low liquidity**.
This shapes everything about how outputs should be framed:

- **Position sizes**: £100 for most positions, up to ~£2,000 for high-conviction
  opportunities. These are not institutional or even affluent-retail numbers. A
  recommendation to "size at 2% of portfolio" means nothing useful here.
- **Long-term orientation**: the default hold period is months to years, not days
  or weeks. The investor is not watching screens, not trading on technicals, and
  not looking for short-term catalysts to play.
- **Soft 3-month minimum hold**: the investor imposes this as a personal discipline
  to avoid reacting to noise, not because they expect the thesis to resolve in 3
  months. It is a floor, not a target. The tool should treat it as standing personal
  context ("factor this when framing exit timing") but never enforce it as a hard
  rule or manufacture a 3-month horizon where the thesis doesn't warrant one.
- **On-demand only**: the tool is run when the investor is actively considering a
  name — never on a timer or as a live feed. It is a research input, not an
  autopilot.
- **The investor always decides**: the tool's output is one input to a human
  decision. It should be honest, not optimistic. Saying "the thesis is weak, don't
  initiate" is more useful than a hedged Hold that doesn't give a clear steer.
- **The investor is new to finance.** Do not assume *any* particular baseline
  of investing vocabulary — even commonly cited "basics" like PE, EPS, market
  cap, dividend yield, support/resistance, beta, and bull/bear are not safely
  assumed to be understood. Any finance, accounting, or trading term beyond
  day-to-day plain English (this includes the so-called basics above, alongside
  more advanced ones like free cash flow conversion, operating leverage, PEG,
  DCF, EV/EBITDA, gross margin, insider ratio, short interest, guidance,
  re-rating, catalyst, moat, drawdown, ATR, etc.) must be glossed briefly in
  plain English the first time it appears in the output. Frame it like writing
  for an intelligent friend who doesn't work in finance: keep the analytical
  content, but make every term land. The investor should finish reading a
  report knowing more than when they started.

### What this means for prompts and outputs

- **Never write as if the investor is institutional.** No "allocate X% of AUM",
  no "build a full position over 3 tranches", no language that assumes deep
  liquidity or the ability to size meaningfully.
- **Write in £ terms where sizing is mentioned.** "A £200 initial position" is
  more useful than "a 2% allocation."
- **Don't invent precision that doesn't exist.** A condition-based hold ("hold as
  long as margins keep expanding") is more honest than a fabricated date horizon.
- **Frame recommendations against actual position status.** The investor provides
  whether they hold the ticker and roughly how much at run time. The output should
  open from that reality — "you hold ~£800 here, the thesis looks intact, sit
  tight" rather than generic boilerplate.
- **Flag data gaps honestly.** yfinance/Alpha Vantage have real coverage gaps,
  especially for non-US names. "No insider transactions reported" should be
  flagged as possible data absence, not treated as a meaningful signal.

---

## Portfolio context

The satellite portfolio sits on top of:
- **Core**: VUAG (Vanguard FTSE All-World UCITS ETF) inside a Stocks & Shares ISA
- **Pension**: diversified, not actively managed
- **Employer share plan**: ~£17k in a single concentrated position

When making changes that affect position sizing or concentration advice, be aware
that the investor already has significant single-stock concentration through the
employer plan. New satellite positions should be assessed against that context, not
in isolation.

---

## Local environment

This repo's Python deps live in a conda env named **`tradingagents`** (managed
via miniforge3). Always activate it before running anything — tests, ruff, the
CLI, `python main.py`, all of it. The base Python on PATH has none of the
project deps.

```bash
source /Users/kennedydike/miniforge3/etc/profile.d/conda.sh && conda activate tradingagents
```

Dev tools (`ruff`, `pytest`, `pytest-subtests`) come from the `[dev]` extras in
`pyproject.toml` and are installed into that same env via
`pip install -e ".[dev]"` (or `pip install "ruff>=0.15" "pytest>=8.0" "pytest-subtests>=0.13"`).

---

## Repo structure

```
tradingagents/
├── agents/
│   ├── analysts/
│   │   ├── fundamentals_analyst.py   # Balance sheet, cashflow, PE, EPS, insider tx
│   │   ├── market_analyst.py         # Technical indicators, price data
│   │   ├── news_analyst.py           # News + macro headlines + prediction markets
│   │   ├── sentiment_analyst.py      # Social media sentiment (structured output)
│   │   └── social_media_analyst.py   # Additional social signal layer
│   ├── researchers/
│   │   ├── bull_researcher.py        # Makes the bull case in the debate
│   │   └── bear_researcher.py        # Makes the bear case in the debate
│   ├── managers/
│   │   ├── research_manager.py       # Judges the bull/bear debate → ResearchPlan
│   │   └── portfolio_manager.py      # Synthesises risk debate → final PortfolioDecision
│   ├── risk_mgmt/
│   │   ├── aggressive_debator.py     # Risk panel: aggressive view
│   │   ├── conservative_debator.py   # Risk panel: conservative view
│   │   └── neutral_debator.py        # Risk panel: neutral view
│   ├── trader/
│   │   └── trader.py                 # Translates ResearchPlan → TraderProposal
│   ├── schemas.py                    # Pydantic schemas for all structured outputs
│   └── utils/
│       ├── agent_states.py           # LangGraph state types (AgentState, debate states)
│       ├── agent_utils.py            # Tool wrappers and instrument context helpers
│       ├── memory.py                 # TradingMemoryLog: append-only markdown decision log
│       ├── structured.py             # Provider-agnostic structured output binding
│       └── [data tool files]         # fundamentals, technical, macro, news, prediction
│
├── dataflows/                        # Data vendor integrations
│   ├── y_finance.py                  # yfinance (default for most data)
│   ├── alpha_vantage*.py             # Alpha Vantage (alternative vendor)
│   ├── fred.py                       # FRED (macro indicators)
│   └── polymarket.py                 # Polymarket prediction markets
│
├── graph/
│   ├── trading_graph.py              # TradingAgentsGraph: main orchestrator class
│   ├── propagation.py                # State initialisation and graph run args
│   ├── setup.py                      # LangGraph graph construction
│   ├── reflection.py                 # Reflector: generates lessons from past outcomes
│   ├── signal_processing.py          # Extracts final BUY/HOLD/SELL from decision text
│   └── conditional_logic.py          # Debate round termination conditions
│
├── llm_clients/                      # Provider abstractions
│   ├── factory.py                    # create_llm_client() dispatcher
│   ├── model_catalog.py              # Supported models per provider
│   ├── anthropic_client.py
│   ├── openai_client.py              # Also used for DeepSeek (OpenAI-compatible)
│   ├── google_client.py
│   └── [other provider clients]
│
└── default_config.py                 # Single source of truth for all config + env overrides

cli/                                  # Rich terminal UI (Typer + Rich)
│   main.py                           # Main CLI entry point with interactive prompts
│   utils.py                          # Provider/model selection, ticker input helpers
│   stats_handler.py                  # LLM call stats tracking callback
│   model_catalog.py                  # CLI model menu options
└── __main__.py                       # `python -m cli` entry point

main.py                               # Quick programmatic entry point (for dev/testing)
```

### Data flow through a run

```
CLI / main.py
  └─ TradingAgentsGraph.propagate(ticker, date)
       ├─ Resolve memory log (prior same-ticker decisions → past_context)
       ├─ Resolve instrument identity (yfinance ticker lookup)
       └─ LangGraph pipeline:
            ├─ [Analysts run in parallel or sequence]
            │    ├─ FundamentalsAnalyst  → fundamentals_report
            │    ├─ MarketAnalyst        → market_report
            │    ├─ NewsAnalyst          → news_report
            │    └─ SentimentAnalyst     → sentiment_report
            ├─ [Bull/Bear debate]
            │    ├─ BullResearcher  ─┐
            │    └─ BearResearcher  ─┴─ N rounds → ResearchManager → investment_plan
            ├─ Trader → trader_investment_plan (entry, stop-loss, sizing)
            ├─ [Risk debate]
            │    ├─ AggressiveDebator  ─┐
            │    ├─ ConservativeDebator─┼─ N rounds
            │    └─ NeutralDebator     ─┘
            └─ PortfolioManager → final_trade_decision
                 └─ _log_state() → results_dir/TICKER/TradingAgentsStrategy_logs/
                 └─ memory_log.store_decision() → ~/.tradingagents/memory/trading_memory.md
```

---

## Key schemas (schemas.py)

| Schema | Producer | Key fields |
|--------|----------|------------|
| `ResearchPlan` | Research Manager | `recommendation` (5-tier), `rationale`, `strategic_actions` |
| `TraderProposal` | Trader | `action` (3-tier), `reasoning`, `entry_price`, `stop_loss`, `position_sizing` |
| `PortfolioDecision` | Portfolio Manager | `rating` (5-tier), `executive_summary`, `investment_thesis`, `price_target`, `time_horizon` |
| `SentimentReport` | Sentiment Analyst | `overall_band`, `overall_score`, `confidence`, `narrative` |

**Rating scales:**
- 5-tier (`PortfolioRating`): Buy / Overweight / Hold / Underweight / Sell
- 3-tier (`TraderAction`): Buy / Hold / Sell

---

## Provider and model setup

- **Default for all nodes**: DeepSeek V4 Pro (`deepseek-v4-pro`) via the OpenAI-
  compatible client. Set via `TRADINGAGENTS_LLM_PROVIDER=deepseek`,
  `TRADINGAGENTS_DEEP_THINK_LLM=deepseek-v4-pro`,
  `TRADINGAGENTS_QUICK_THINK_LLM=deepseek-v4-flash`.
- **Closed model (reserved)**: Claude Sonnet 4.6 — for tiebreaking when open models
  disagree, and for final synthesis on high-conviction calls involving meaningful new
  money. Not the default.
- **Multi-provider cross-checking**: longer-term intent to run through 2+ open-weight
  providers (DeepSeek, Qwen, GLM) and treat convergence/divergence as a signal.
  Not yet built.

---

## Things to never do when making changes

- Do not add mandatory date-style time horizons. The model must be free to give
  condition-based answers about duration.
- Do not remove `entry_price`, `stop_loss`, or `position_sizing` from `TraderProposal`.
  These are wanted.
- Do not write prompts that assume institutional position sizing or active trading
  cadence. This is a retail, low-liquidity, long-term context.
- Do not let technical/market signals bleed into the directional call. Market analyst
  output informs entry timing and stop-loss calibration; it does not override the
  fundamentals/debate-driven Buy/Sell direction.
- Do not schedule or automate the main analysis run. On-demand only.
- Do not replace `trading_memory.md` — the audit log (3.5) sits alongside it, not
  in place of it.
