"""
System R Risk Intelligence Integration for TradingAgents
=========================================================

This example shows how to add System R (https://systemr.ai) as an external
risk-validation layer on top of TradingAgents' built-in risk debate.

How it works:
  1. TradingAgents runs its normal analyst -> trader -> risk-debate pipeline.
  2. Before the final decision is acted on, this wrapper calls System R's
     pre-trade-gate API to get an independent risk assessment.
  3. If System R vetoes the trade (gate="FAIL"), the decision is downgraded
     to HOLD regardless of what the internal agents decided.

The pre-trade gate evaluates position sizing, drawdown limits, correlation
risk, and concentration against the portfolio equity you supply.

Prerequisites:
  pip install requests tradingagents

Environment variables:
  SYSTEMR_API_KEY   - your System R API key (get one at https://systemr.ai)

For a full standalone trading agent with System R risk management, see:
  https://github.com/System-R-AI/demo-trading-agent
"""

import os
import re
import requests
from typing import Tuple, Optional
from dotenv import load_dotenv

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

load_dotenv()

# ---------------------------------------------------------------------------
# System R pre-trade gate
# ---------------------------------------------------------------------------

SYSTEMR_PRE_TRADE_GATE_URL = "https://agents.systemr.ai/v1/compound/pre-trade-gate"


def call_systemr_pre_trade_gate(
    symbol: str,
    direction: str,
    entry_price: float,
    stop_price: float,
    equity: float,
    api_key: Optional[str] = None,
) -> dict:
    """Call System R's pre-trade-gate API for independent risk validation.

    The gate checks position sizing, drawdown limits, correlation risk, and
    portfolio concentration before a trade is executed.

    Args:
        symbol:      Ticker symbol, e.g. "NVDA".
        direction:   "LONG" or "SHORT".
        entry_price: Planned entry price.
        stop_price:  Planned stop-loss price.
        equity:      Total portfolio equity in USD.
        api_key:     System R API key (falls back to SYSTEMR_API_KEY env var).

    Returns:
        API response dict.  Key fields:
          - gate:    "PASS" or "FAIL"
          - checks:  list of individual risk checks and their results
          - summary: human-readable explanation

    Raises:
        requests.HTTPError on non-2xx responses.
    """
    key = api_key or os.getenv("SYSTEMR_API_KEY", "")
    headers = {
        "Content-Type": "application/json",
    }
    if key:
        headers["X-API-Key"] = key

    payload = {
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "equity": equity,
    }

    resp = requests.post(
        SYSTEMR_PRE_TRADE_GATE_URL,
        json=payload,
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Wrapper that adds System R validation to TradingAgentsGraph
# ---------------------------------------------------------------------------


def extract_decision(signal_text: str) -> str:
    """Pull BUY / SELL / HOLD from the final signal text."""
    match = re.search(r"\b(BUY|SELL|HOLD)\b", signal_text.upper())
    return match.group(1) if match else "HOLD"


def run_with_systemr_risk_gate(
    ticker: str,
    trade_date: str,
    equity: float = 100_000.0,
    entry_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    config: Optional[dict] = None,
) -> Tuple[str, dict, dict]:
    """Run TradingAgents and validate the result through System R.

    Args:
        ticker:      Stock ticker symbol (e.g. "NVDA").
        trade_date:  Date string (e.g. "2024-05-10").
        equity:      Portfolio equity for risk sizing (default $100k).
        entry_price: Planned entry price.  If None, a placeholder is used.
        stop_price:  Planned stop-loss price.  If None, defaults to 2% below
                     entry for BUY, 2% above entry for SELL.
        config:      Optional TradingAgents config dict override.

    Returns:
        Tuple of (final_decision, full_signal, systemr_response).
    """
    # 1. Run the standard TradingAgents pipeline
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    ta = TradingAgentsGraph(debug=False, config=cfg)
    full_signal, decision = ta.propagate(ticker, trade_date)

    internal_decision = extract_decision(decision)
    print(f"[TradingAgents] Internal decision: {internal_decision}")

    # Nothing to gate if the agents already say HOLD
    if internal_decision == "HOLD":
        print("[System R] Skipping gate -- internal decision is HOLD.")
        return internal_decision, full_signal, {}

    # 2. Determine direction and prices for the gate
    direction = "LONG" if internal_decision == "BUY" else "SHORT"

    # Use provided prices or sensible defaults
    _entry = entry_price or 100.0  # placeholder when price is unknown
    if stop_price is None:
        # Default: 2% adverse move
        _stop = _entry * 0.98 if direction == "LONG" else _entry * 1.02
    else:
        _stop = stop_price

    # 3. Call System R pre-trade gate
    print(f"[System R] Calling pre-trade gate for {ticker} {direction} ...")
    try:
        gate_result = call_systemr_pre_trade_gate(
            symbol=ticker,
            direction=direction,
            entry_price=_entry,
            stop_price=_stop,
            equity=equity,
        )
    except requests.RequestException as exc:
        # If the external service is unreachable, log and fall through to
        # the internal decision (fail-open).  Change to fail-closed if you
        # prefer safety over availability.
        print(f"[System R] Gate unavailable ({exc}); using internal decision.")
        return internal_decision, full_signal, {}

    gate_verdict = gate_result.get("gate", "UNKNOWN")
    print(f"[System R] Gate verdict: {gate_verdict}")

    if gate_result.get("summary"):
        print(f"[System R] Summary: {gate_result['summary']}")

    # 4. Apply the gate
    if gate_verdict == "PASS":
        final_decision = internal_decision
        print(f"[Final] Trade APPROVED -- executing {final_decision}.")
    else:
        final_decision = "HOLD"
        print("[Final] Trade BLOCKED by System R risk gate -- downgrading to HOLD.")

    return final_decision, full_signal, gate_result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Configure TradingAgents (adjust models to your preference)
    config = DEFAULT_CONFIG.copy()
    config["deep_think_llm"] = "gpt-4o"
    config["quick_think_llm"] = "gpt-4o-mini"
    config["max_debate_rounds"] = 1

    # Run with System R gate
    final, signal, gate = run_with_systemr_risk_gate(
        ticker="NVDA",
        trade_date="2024-05-10",
        equity=100_000,
        config=config,
    )

    print("\n" + "=" * 60)
    print(f"FINAL DECISION: {final}")
    if gate:
        print(f"RISK GATE:      {gate.get('gate', 'N/A')}")
    print("=" * 60)
