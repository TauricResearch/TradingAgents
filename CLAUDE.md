# TradingAgents

Multi-agent LLM financial trading framework (fork of TauricResearch/TradingAgents) plus a
personal finance assistant service layered on top. Research output — not financial advice.

## Commands

```bash
pip install -e ".[dev,assistant]"   # dev install: core + assistant service + pytest/ruff
tradingagents                       # interactive analysis CLI (typer app: cli.main:app)
uvicorn app.main:app                # assistant dashboard + scheduler at http://127.0.0.1:8000
pytest                              # test suite
ruff check .                        # lint
```

## Architecture — two systems in one repo

| Path | What it is |
|------|------------|
| `tradingagents/` | Core framework: analyst → bull/bear debate → trader → risk team → portfolio manager agents wired as a LangGraph graph; multi-provider LLM registry (OpenAI, Anthropic, Gemini, Ollama, Bedrock, any OpenAI-compatible endpoint); data vendors (Alpha Vantage, FRED, Polymarket, yfinance) |
| `cli/` | Typer CLI entry point (`tradingagents` command) |
| `app/` | Assistant service — FastAPI + APScheduler + async SQLAlchemy: scheduled watchlist runs with per-slot budgets, ticker rotation, Telegram/email alerts, paper trading, dashboard UI in `app/static/`. Full docs in `app/README.md` |
| `tests/` | Pytest suite covering both systems (`test_assistant_*` for the app layer) |

`app/` follows api / core / models / repositories / services layering: business logic in
services, DB access in repositories, routes thin.

## Environment

- Copy `.env.example` → `.env`. Framework config via `TRADINGAGENTS_*` env vars
  (provider, models, API keys — keys auto-detected); assistant config via `ASSISTANT_*`
  (e.g. `ASSISTANT_DAILY_RUN_BUDGET`, default 4 ticker-runs/day).
- Runtime data lives in `~/.tradingagents/`: `assistant.db` (SQLite signal history),
  `logs/reports/` (markdown analysis reports).
- The uvicorn process must be running for scheduled slots to fire; a run missed while
  the machine slept fires within an hour of wake-up.

## Gotchas

- **Windows `.env`**: write BOM-free — PowerShell 5.1 `-Encoding utf8` corrupts the first key.
- **LLM budget**: default schedule respects the Ollama-cloud free tier (~10–12 full runs/week);
  slots analyze the *stalest* due tickers first, so the watchlist still rotates fully.
- **Timestamps are UTC** in the DB; UI parsing depends on it — don't store local times.
- **Watchlist rotation**: 5 consecutive Holds demote a ticker to weekly check-ins; any
  actionable rating (Buy/Sell/Over-/Underweight) promotes it back to daily. Nothing is
  auto-deleted — history feeds the engine's self-reflection loop.
- **Paper trading**: when verifying "did it work?", compare against the recorded baseline
  in the DB rather than re-deriving prices. Compare books and benchmark over the **same
  window** (`equity_snapshots` may start later than the account), count only **closed**
  forward-return windows, and report **effective** sample size — overlapping windows on
  correlated names are not independent observations.
- **Idle cash is an unfunded short against SPY.** The index core (`app/services/core_holding.py`)
  sweeps uncommitted capital into `CORE_ETF` so its resting state is market return, not zero.
  Core positions are marked `note="core"`, are never stopped out, and are sold only to fund a
  satellite signal. This is an accounting fix, not a forecast — it needs no edge to be correct.
- **Nine alpha routes were tested and failed** (Aug 2026): per-ticker strategy selection,
  timing rules vs an exposure-matched cash blend, cross-sectional price ML and fundamental ML
  on point-in-time universes, cross-asset/dual momentum, LLM signals, VLM chart reading,
  Kronos, and OpenBB. Each had a working control. Before proposing a tenth, read the verdicts
  — and always include a random-feature control and an exposure-matched benchmark.
