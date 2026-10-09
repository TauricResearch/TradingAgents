# Paper-only trading guard (phase 1)

This is the first isolated step toward auditable crypto paper trading. It does
**not** trade and does **not** change the TradingAgents CLI or existing agents.

The existing TraderProposal uses Buy / Sell / Hold as an **analysis proposal**;
PortfolioDecision uses five position ratings. Neither is a broker order. The
new TradeIntent must be constructed explicitly from an operator-reviewed
decision. There is intentionally no automatic conversion from the text SELL.

## Validation contract

- Actions: HOLD, SPOT_BUY, SPOT_SELL, SHORT_OPEN, SHORT_CLOSE (the last
  is rejected until short-position accounting is implemented).
- PAPER is the **only** supported execution mode.
- A market-specific action cannot be used with the wrong market.
- The proposal requires an explicit order type, base-asset quantity and
  idempotency key; LIMIT requires a price.
- A fresh, timestamped, matching-symbol quote and known portfolio balances
  are mandatory. Future quotes and stale quotes are blocked.
- New long/short exposures need a correctly oriented stop and take-profit,
  have a 5% equity notional cap and 1% theoretical stop-loss budget by default.
- Spot sells may only reduce currently available base asset balances.
- Leveraged positions, live execution and short closing are **not supported**.

Theoretical stop loss is *not* guaranteed maximum loss. It excludes slippage,
fees, liquidations, spread, exchange minimum sizes, partial fills, stop failures
and funding. Rejecting a proposal here does not imply every approved proposal
is suitable for real execution.

Example (standalone; never sends an order):

    from datetime import datetime, timezone
    from tradingagents.trade_guard import (
        MarketSnapshot, PortfolioSnapshot, TradeIntent, validate_intent,
    )

    now = datetime.now(timezone.utc)
    proposal = TradeIntent(
        symbol="BTC-USD", market="PERPETUAL", action="SHORT_OPEN",
        order_type="LIMIT", quantity_base="0.025", limit_price="84500",
        stop_loss="87800", take_profit="80000",
        idempotency_key="demo-btc-01",
    )
    quote = MarketSnapshot(
        symbol="BTC-USD", price="82403.44",
        observed_at=now, source="paper-test",
    )
    account = PortfolioSnapshot(
        equity_quote="100000", free_quote="10000", free_base="0.3",
    )
    print(validate_intent(proposal, quote, account, now=now))

## What is intentionally out of scope

1. Parsing a free-text SELL into an order or connecting to the live CLI flow.
2. Paper order storage, duplicate-key rejection, simulated fills, stop
   execution and position reconciliation.
3. Verified exchange OHLCV feed for BTC/BRL, per-instrument fee models,
   derivative margin/liquidation rules and live trading.

The guard cannot be connected to an exchange until these later stages have
their own tests and explicit review.

Run the isolated tests with:

    python -m pytest tests/test_trade_guard.py -q
