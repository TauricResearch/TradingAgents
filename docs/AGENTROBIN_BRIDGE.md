# agentRobin brokerage bridge

Loads paper and live accounts from the sibling [agentRobin](https://github.com/klepsydra/agentRobin)
tree into TradingAgents `PortfolioContext` (ROBIN-1689).

## Quick use

```bash
export AGENTROBIN_ROOT=/home/marckoby/dev/agentRobin
tradingagents --account FakeAcct.01 --ticker NVDA
```

`--account` wins over `--portfolio`. List accounts:

```bash
ruby "$AGENTROBIN_ROOT/scripts/tradingagents_bridge.rb" accounts
```

## Env

| Variable | Purpose |
|----------|---------|
| `AGENTROBIN_ROOT` | Path to agentRobin (CLI subprocess bridge) |
| `TRADINGAGENTS_AGENTROBIN_URL` | Optional HTTP bridge base (`http://127.0.0.1:8793`) |
| `TRADINGAGENTS_AGENTROBIN_TOKEN` | Bridge token (or `AGENTROBIN_TRADINGAGENTS_BRIDGE_TOKEN`) |
| `AGENTROBIN_TRADINGAGENTS_ALLOW_LIVE` | Must be `1` on agentRobin host for live place |

Live equity placement is available via `tradingagents.brokerages.place_equity_order(..., allow_live=True)` but stays gated. Analysis/portfolio load never places orders.

## Module

`tradingagents/brokerages/agentrobin.py` — `list_accounts`, `fetch_portfolio`, `place_equity_order`.
