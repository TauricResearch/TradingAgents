# Phase 2: crypto decision review (paper only)

This phase **does not execute orders**. It wires the existing analyst/Trader/
Portfolio Manager final state to a fail-closed review at the common
\`TradingAgentsGraph.record_decision()\` path used by CLI and Python.

For \`asset_type="crypto"\`, the final state gains:
- \`trade_guard_review\`: machine-readable BLOCKED status and reason codes.
- \`trade_guard_report\`: human-readable review saved at
  \`6_trade_guard/review.md\` and in the consolidated Markdown/HTML report.

A 5-tier rating is not an executable order. In particular, a portfolio rating
"Sell" does not distinguish a spot exit from opening a derivative short. No
prices, market types, holdings, order quantities or stop orders are inferred
from free-text prose. The review is always BLOCKED until a different caller
explicitly provides validated PAPER intent and independently sourced data.

Example of a **manual paper-only validation** (does not place an order):

    from datetime import datetime, timezone
    from tradingagents.trade_guard import MarketSnapshot, PortfolioSnapshot, TradeIntent
    from tradingagents.trade_guard.review import validate_paper_decision

    # "final_state" must be the actual completed crypto analysis state.
    now = datetime.now(timezone.utc)
    intent = TradeIntent(
        symbol="BTC-USD", market="PERPETUAL", action="SHORT_OPEN",
        order_type="LIMIT", quantity_base="0.025", limit_price="84500",
        stop_loss="87800", take_profit="80000", idempotency_key="demo-01",
    )
    snapshot = MarketSnapshot(
        symbol="BTC-USD", price="82403", observed_at=now,
        source="external-paper-test",
    )
    balances = PortfolioSnapshot(
        equity_quote="100000", free_quote="10000", free_base="0.0",
    )
    verdict = validate_paper_decision(
        final_state, intent, snapshot, balances, now=now,
    )

Even when \`verdict.approved\` is True, it is **only approval to proceed to a
future paper simulator**. There is still no execution engine, order storage,
deduplication, live integration, fill model, fee/funding model or stop guarantee.
The user/operator must independently verify the quote and balances.

Run isolated tests:

    python -m pytest tests/test_crypto_decision_review.py -q

Full project checks:

    python -m pytest -q
    ruff check .
