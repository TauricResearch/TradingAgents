# Contributing to this TradingAgents fork

Thanks for showing up. This repo is a fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents): a multi-agent research desk that studies **one ticker at a time**. The fork's extra job is a small **Execution Agent** that reads the Trader and Portfolio Manager write-up and either:

- **recommends** buy / hold / sell plus a **percent of available cash**, or
- when you opt in, **places that ticket** on Alpaca **paper** trading.

If you want to help, the highest-leverage work is making that last mile clearer, safer, and better tested — without turning the desk into a basket allocator or a live-trading bot.

Please keep the upstream citation in the README. This is their research framework; we are adding a paper-trade handoff.

## What we are building (and not building)

**In scope**

- Single-ticker analysis
- A recommendation on every run
- Optional Alpaca paper fills
- Sizing against **usable cash**, never against total equity or money already in stocks
- Honoring the PM **time horizon** and selling on the plan's **stop** (significant loss)

**Out of scope**

- An 8-stock basket or portfolio rotation engine
- “Fixing” sizing to use total capital / equity
- Defaulting to live Alpaca
- Committing `.env` files, API keys, journals, or order dumps

## Dev setup

```bash
git clone https://github.com/Philemon518/TradingAgents.git
cd TradingAgents
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install ".[dev]"
cp .env.example .env        # fill keys locally; never commit this file
```

Use paper Alpaca keys if you want a real simulator. Tests do **not** need them.

## Tests

The full suite:

```bash
pytest
```

The execution subset (fake Alpaca, no network, no keys):

```bash
pytest tests/test_position_plan.py \
       tests/test_execution_parser.py \
       tests/test_execution_agent.py \
       tests/test_execution_reporting.py \
       tests/test_env_overrides.py -q
```

If you touch `default_config.py`, keep `tests/test_env_overrides.py` green.

Ruff is configured in `pyproject.toml` (`line-length = 100`, `target-version = py310`). Prefer matching nearby style over a repo-wide format pass.

### How to add an execution test

1. Put a **fake Alpaca client** on `ExecutionAgent(..., client=fake)`. Do not call the real API.
2. Give the fake distinct `cash` and `equity` (for example cash `$2,000`, equity `$12,000`). A 50% buy must spend **$1,000**, not $6,000.
3. Assert `submit_order` is **never** called when `execution_enabled` is false.
4. For horizon tests: open a paper buy on an early date, then either drop `current_price` through the stop (must sell) or jump past `horizon_end_date` with a PM Sell (must sell).
5. Never hard-code secrets. Empty strings are fine.

## Where the code lives

| Path | Role |
|------|------|
| `tradingagents/agents/` | Research desk (analysts, trader, PM) |
| `tradingagents/graph/` | LangGraph wiring; `execute_trade_decision()` runs after the PM |
| `tradingagents/execution/parser.py` | Prose → rating, prices, horizon, cash % |
| `tradingagents/execution/position_plan.py` | Stored hold window + stop |
| `tradingagents/execution/agent.py` | Recommendation + optional paper order |
| `tradingagents/execution/journal.py` | Local markdown trail (no keys) |
| `tradingagents/reporting.py` | Writes `6_execution/execution.md` |
| `cli/main.py` | Single-ticker CLI display |
| `tests/test_execution_*.py` | Fake-client contract |

The research graph still ends at the Portfolio Manager. Execution is a **post-graph** step, not a new debate node.

## Pull requests

- One logical change per PR. Split files into focused commits when you can (parser, then agent, then tests).
- Do not mix a CLI tweak with a sizing-rule change.
- Do not “improve” cash-percent math into equity-percent math.
- Paper remains the default. If you add a live-URL path, keep the warning and do not enable it by default.
- Never stage `.env`, `execution_journal.md` with account data, or `reports/` from a personal run.

## Reporting bugs

Include:

- Ticker and analysis date
- Whether `TRADINGAGENTS_EXECUTION_ENABLED` was true
- The recommendation you expected vs what you saw (`order_action`, `cash_allocation_pct`)

Do **not** paste API keys, account numbers, or full Alpaca JSON dumps.

## Credit

TradingAgents is the work of Yijia Xiao, Edward Sun, Di Luo, and Wei Wang. Please cite their paper if the framework helps you — the README has the BibTeX. This fork's execution layer is an add-on for paper simulation, not a replacement for that research.
