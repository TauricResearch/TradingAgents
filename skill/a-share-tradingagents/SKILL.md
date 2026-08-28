---
name: a-share-tradingagents
description: Analyze mainland China A-share positions with the bundled TradingAgents framework. Use for A-share valuation, trend, portfolio-aware add or reduce decisions, position sizing, China-market data, trading constraints, risk controls, CLI runs, environment checks, and framework diagnostics.
---

# A股智能仓位管理

## Locate the framework

Resolve the framework in this order:

1. Use `A_SHARE_TRADINGAGENTS_HOME` when it points to the repository's `framework` directory.
2. If this skill is inside a cloned repository, use `..\..\framework` relative to the skill directory.
3. If neither path works, ask the user where the repository was cloned.

Use `<framework>\.venv\Scripts\python.exe` and
`<framework>\.venv\Scripts\tradingagents.exe` directly. Never print API keys or
upload `.env`.

## Manage positions

Treat bare six-digit mainland codes and `.SH`/`.SS`/`.SZ`/`.BJ` symbols as
`asset_type="a_share"`. Return one position action:

- `Add`
- `Slight Add`
- `Hold`
- `Reduce`
- `Exit`

Collect position context before giving a personalized action:

- `cost_basis`
- `position_pct`
- `shares`
- `cash_available` when known
- `holding_horizon_days`
- `max_drawdown_pct`
- `bought_today`

Use the deterministic valuation-trend-position matrix as the baseline, then
check company evidence and portfolio constraints. Report data failures and
lower confidence instead of inventing values.

## Use A-share data and rules

Use Eastmoney first, Tencent Finance as the Chinese-market fallback, and Yahoo
Finance only if both Chinese vendors fail. Include the Shanghai Composite,
CSI 300, Shenzhen Component, and ChiNext market environment.

Enforce T+1, 100-share buy lots, board-specific price limits, odd-lot selling,
fees and slippage, maximum drawdown, and concentration limits. Do not replace
the A-share path with FRED, Polymarket, Reddit, or StockTwits signals.

## Run

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

graph = TradingAgentsGraph()
state, action = graph.propagate(
    "600968",
    "2026-07-23",
    portfolio_context={
        "cost_basis": 3.65,
        "position_pct": 8,
        "shares": 10000,
        "holding_horizon_days": 120,
        "max_drawdown_pct": 10,
        "bought_today": False,
    },
)
```

Before a full multi-agent run, verify that `<framework>\.env` contains a
configured LLM provider key without displaying its value. If no key exists,
run only deterministic data checks and state that the LLM debate did not run.

## Validate changes

Run from `<framework>`:

```powershell
.\.venv\Scripts\python.exe -m compileall -q tradingagents cli
.\.venv\Scripts\python.exe -m pytest tests\test_a_share_mode.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_signal_processing.py tests\test_symbol_utils.py tests\test_cli_symbol_handling.py -q
```

Treat all output as research support, not financial advice.
