# Contributing

Thanks for helping improve this fork. The goal is simple: **turn AI analysis into Alpaca paper trades** — safely, clearly, and with good tests.

This builds on [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents). Keep their citation in the README.

---

## Get started in 5 minutes

```bash
git clone https://github.com/Philemon518/TradingAgents.git
cd TradingAgents
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install ".[dev]"
cp .env.example .env                 # fill keys locally — never commit this file
```

Run tests (no Alpaca keys needed):

```bash
pytest
```

Run only execution tests:

```bash
pytest tests/test_execution_*.py tests/test_env_overrides.py -q
```

Run the CLI locally:

```bash
set -a && source .env && set +a
tradingagents
```

Note: the command is `tradingagents`, not `tradingagents analyze`.

---

## What belongs in this fork

**Yes**

- Single-ticker execution (one stock per run)
- Alpaca **paper** orders by default
- Buy/hold/sell + **percent of available cash** sizing
- Respecting PM time horizon and stop-loss rules
- Tests with a fake Alpaca client (no network)
- Docs and bug fixes

**No**

- Multi-stock basket / portfolio rotation
- Sizing against total equity instead of cash
- Live trading enabled by default
- Committing `.env`, API keys, journals, or personal `reports/`

---

## Project layout

```
tradingagents/
  agents/           # Analysts, trader, PM (upstream research desk)
  graph/            # LangGraph wiring; execute_trade_decision() after PM
  execution/
    parser.py       # PM/trader text → action, prices, horizon, cash %
    position_plan.py # Hold window + stop-loss tracking
    agent.py        # Recommendation + Alpaca paper order
    journal.py      # Local markdown log
  default_config.py # Defaults + TRADINGAGENTS_* env overrides
cli/main.py         # Interactive CLI
tests/test_execution_*.py
```

Execution runs **after** the research graph finishes. It is not a new debate agent.

---

## Writing tests

Execution tests use a **fake Alpaca client** — never call the real API in CI.

```python
agent = ExecutionAgent(config, client=fake_client)
result = agent.run(ticker="NVDA", portfolio_manager_text=pm_text, trade_date="2026-03-01")
```

Rules:

1. Give the fake different `cash` and `equity` (e.g. cash $2,000, equity $12,000). A 50% buy must spend **$1,000**, not $6,000.
2. When `execution_enabled=False`, assert `submit_order` is never called.
3. For horizon tests: buy on date A, then test stop breach or horizon expiry + PM Sell.
4. No hard-coded secrets.

If you change `default_config.py`, run `tests/test_env_overrides.py`.

Style: Ruff in `pyproject.toml` (line length 100). Match nearby code.

---

## Pull requests

1. One logical change per PR when possible (parser, then agent, then tests).
2. Run `pytest` before opening.
3. Do not change cash sizing to use equity.
4. Paper trading stays the default; live URLs must keep a warning.
5. Never stage `.env`, journals with account data, or personal reports.

---

## Reporting bugs

Include:

- Ticker and analysis date
- Whether execution was on (`TRADINGAGENTS_EXECUTION_ENABLED`)
- Expected vs actual: `order_action`, `cash_allocation_pct`, error message

Do **not** paste API keys, account numbers, or full Alpaca JSON.

---

## Credit

TradingAgents: Yijia Xiao, Edward Sun, Di Luo, Wei Wang — see README for BibTeX. This fork adds a paper-trade execution layer on top of their research framework.
