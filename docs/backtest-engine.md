# Backtest Engine MVP

`run_daily_signal_backtest` is the first deterministic backtest layer:

```python
from tradingagents.research_platform.backtest_engine import run_daily_signal_backtest
```

Inputs:

- `BacktestConfig`
- normalized `PriceBar` records
- validated `TradeSignal` records

The engine does not read LLM prose. Legacy decisions must first be converted to
`TradeSignal` through the agent artifact bridge.

## Execution Rules

- A signal executes on the first available price bar after `signal.as_of_date`.
- The execution price is the daily close adjusted by configured slippage.
- Commission is charged in basis points on traded notional.
- `Buy` targets `signal.proposed_position_pct` of current equity.
- `Sell` closes the position unless shorting is enabled.
- `Hold` does not trade.

## Metrics

The MVP reports:

- total return
- CAGR when the date range is long enough
- annualized volatility
- Sharpe
- Sortino
- max drawdown
- turnover
- average gross exposure

This is intentionally simple and deterministic. It is a correctness baseline
before adding richer portfolio accounting, benchmark alpha, rebalancing, and
strategy parameter sweeps.
