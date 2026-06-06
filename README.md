<div align="center">

# 🤖 trading-agent

**An autonomous, multi-agent AI investment fund** — LLM reasoning on top of a
deterministic risk & execution engine.

*Design-first · DB-first · test-driven · built to a written architecture spec*

![status](https://img.shields.io/badge/status-alpha%20v0-orange)
![python](https://img.shields.io/badge/python-3.13-blue)
![tests](https://img.shields.io/badge/tests-216%20passing-brightgreen)
![stack](https://img.shields.io/badge/LangGraph-OpenRouter%2FDeepSeek-purple)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

</div>

---

A research project exploring how to run a **portfolio-managing AI fund** the way
a real desk works: a team of specialist analyst agents that gather their own
data, debate a thesis, and hand it to a deterministic risk gate and trade
function. The LLMs do the *reasoning*; everything quantitative — position
sizing, price levels, guardrails, execution, exits — is deterministic, tested
Python.

> ⚠️ Educational / research project. **Paper trading only**, not financial
> advice. The codebase mirrors a separate design wiki (`architettura.canvas`):
> states, nodes and edges follow the spec, not an inherited framework.

## ✨ What this project demonstrates

- **Multi-agent orchestration** with LangGraph — a real graph of agents
  (2 desks → Portfolio Manager → Risk Analyst) with a "when in doubt, ask" loop.
- **Autonomous tool-calling** — each agent calls its own tools (the *Extractors
  set*), fetches real-time-first data and writes it through to the DB.
- **Per-agent memory** — every agent keeps a structured context window tailored
  to its task, accumulating across the analysis.
- **Deterministic risk core** — ATR-based entry/stop/target, risk-based sizing
  with portfolio heat, an institutional "Statute" (R:R, 10% cash reserve, VaR,
  sector caps), exit management and rating-based disinvestment.
- **DB-first data layer** — time-series + documents in one engine
  (SQLite → PostgreSQL/TimescaleDB), double-dated to prevent look-ahead bias.
- **Swappable broker adapter**, idempotent orders, crash reconciliation.
- **A deterministic backtester** to validate the thresholds.
- **216 offline tests** — no network, no keys: fake LLM + fake fetchers as the
  oracle that the code matches the design.

## 🧠 How it works

The only non-deterministic part is the **brain** (the LLM agents). They fill the
investment thesis; the rest is tested Python.

```
autonomous loop (periodical synthesis)
  └─ Trigger Engine        checkpoints · price alerts · screening
       └─ priority queue
            └─ BRAIN per ticker     ── warm start: extractors pre-run → first context
                 ├─ Market · Sentiment        (Analyst Research)
                 ├─ Technical · Fundamentals  (Analyst Technical)
                 │     ↑ each agent calls its own tools (Extractors set) → DB
                 ├─ Portfolio Manager   aggregates direction/conviction + ATR levels
                 └─ Risk Analyst        bear case + Statute (R:R · cash · VaR · sector)
                      └─ Investment State → deterministic Trade (equity / options on Strong)
                           └─ broker (paper) → exits (TP/SL) · disinvestment
                                └─ DecisionLog  (learning substrate)
```

## 🧱 Architecture / code map

| Package | Responsibility |
|---------|----------------|
| `storage/` | DB-first persistence (market data · ticker card · research states · trades · charter) |
| `domain/` | `ResearchState`, enums, risk engine (ATR levels, sizing, Statute guardrails) |
| `indicators/` | pure technical indicators (`compute_indicator`) |
| `ingestion/` | vendor → DB extractors (prices · news · fundamentals · macro · social), DB-first |
| `tools/` · `brain/tooling.py` | the Extractors set: tools agents call (real-time-first + write-through) |
| `brain/` | the LangGraph: 2 desks → PM → Risk; per-agent context windows |
| `execution/` | deterministic Trade, net-EV cost gate, exits, disinvestment, mantainer |
| `broker/` | swappable adapter (PaperBroker · Alpaca) + commission models |
| `orchestration/` | Trigger Engine + cycle runner + autonomous loop |
| `backtesting/` | deterministic threshold validator |
| `app.py` · `cli.py` | runnable entry point |

## 🛠️ Tech stack

Python 3.13 · LangGraph / LangChain · OpenRouter + DeepSeek (configurable) ·
SQLAlchemy 2 (SQLite / PostgreSQL + TimescaleDB) · Pydantic · pytest · `uv`.

## 🚀 Quick start

```bash
uv sync

# configure .env (see .env.example) — at minimum OPENROUTER_API_KEY
# optional: FRED_API_KEY (macro), ALPACA_* (live broker)

# one analysis cycle
uv run python -m tradingagents.cli AAPL MSFT --start 2024-01-01

# autonomous paper-trading loop, every hour
uv run python -m tradingagents.cli AAPL MSFT --loop 3600
```

## ✅ Testing

```bash
uv run pytest -m "not integration"   # fast, offline, deterministic
uv run pytest -m integration         # network: yfinance · Alpaca · LLM
```

The offline suite needs no network and no API keys — the brain runs against a
fake LLM and the vendors against fake fetchers, so the tests are a true oracle
for the design.

## 🧭 Design philosophy

- **LLMs reason, code computes.** Numbers come from tools and deterministic
  functions, never from the model's head.
- **Real-time first, write-through.** Live data is fetched fresh and persisted;
  the DB stays the single source of truth.
- **Few strong agents, not many weak ones.** Specialised desks with powerful
  tools, minimal context rot.
- **Alpha-first / incremental.** Get a running slice, then deepen.

## 🛣️ Roadmap

- **Read-only dashboard** (Streamlit, SFC-fund style): portfolio, NAV,
  performance/attribution, decisions and trades — observe, never control.
- **Observability & evaluation**: LangSmith + LangGraph Studio for graph
  tracing, agent debugging and prompt evaluation.
- **Inter-task agent memory** (learn from past cases) + systematic DB dedup.
- **Live execution**: IBKR adapter, real options chain, service wrapper
  (24/7, market-hours scheduling, crash recovery).
- **Parameter tuning** in backtest.

## 📜 License

MIT.
