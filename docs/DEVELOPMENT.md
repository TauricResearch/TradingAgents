# TradingAgents Pro — Developer Guide

## Setup

```bash
git clone <repo> ~/dev/TradingAgents          # NOT inside an iCloud-synced path
python3 -m venv ~/.venvs/tradingagents-pro    # venv outside the repo tree
~/.venvs/tradingagents-pro/bin/pip install -e "~/dev/TradingAgents[dev,dashboard]"
```

> **macOS warning:** never place the repo or its venv under `~/Documents`
> (or any iCloud-synced folder). iCloud sync can wedge file vnodes in
> uninterruptible kernel waits, freezing builds and tests (ADR-0013).

Optional extras: `qdrant` (memory vector backend), `dashboard`
(FastAPI UI), `bedrock` (base framework's AWS provider).

## Everyday commands

```bash
pytest -q                                  # full suite (base + Pro)
ruff check .                               # lint (auto-fix: --fix)
python scripts/pro_dashboard_demo.py       # dashboard on :8600 with demo data
python scripts/pro_benchmark.py            # orchestration benchmarks
```

Only `FRED_API_KEY` (free) is needed for the implemented live feeds; the
test suite requires no keys or network at all.

## Layout

| Path | What lives there |
|---|---|
| `tradingagents/contracts/` | Frozen Pydantic contracts every phase speaks (schema 0.2) |
| `tradingagents/pro/ingestion/` | Typed gold/BTC feed adapters → `MarketSnapshot` |
| `tradingagents/pro/agents/` | `EvidenceAgent` runtime + 59-spec roster + prompt files |
| `tradingagents/pro/analytics/` | Deterministic quant features + risk engine |
| `tradingagents/pro/pipeline/` | LangGraph debate pipeline (parallel teams, gates, human approval) |
| `tradingagents/pro/memory/` | JSONL memory + vector retrieval + knowledge graph |
| `tradingagents/pro/backtest/` | Replay engine, sim broker, LLM cache, walk-forward, Monte Carlo |
| `tradingagents/pro/rl/` | Tabular advisory policy (`PolicyProtocol` seam for deep RL) |
| `tradingagents/pro/execution/` | Router, safety rails, paper venue adapters, audit log |
| `tradingagents/pro/dashboard/` | View models + FastAPI shell + template |
| `tradingagents/pro/service.py` | The deployable paper-trading loop |
| `tradingagents/pro/observability.py` | JSON logs, metrics, LLM cost tracking |
| `docs/` | `DATA_SOURCES.md`, `DEPLOYMENT.md`, analysis docs |
| `ARCHITECTURE.md`, `DECISIONS.md` | Living architecture + ADR log (read these first) |

## House rules (from the ADR log)

1. **LLMs never compute numbers.** Deterministic code produces every
   metric; agents interpret and must cite what they were shown.
2. **Abstention over fabrication.** Missing input ⇒ the agent returns
   nothing; gates fail closed.
3. **Contracts are frozen and `extra="forbid"`.** Schema drift fails
   loudly; bump `SCHEMA_VERSION` on shape changes.
4. **Every phase's tests stay green.** The base stock workflow's suite is
   part of the gate; Pro code never edits base modules.
5. **Tests run offline.** Injectable transports/loaders/LLMs everywhere;
   canned payloads live in `tests/pro_fakes.py`.
