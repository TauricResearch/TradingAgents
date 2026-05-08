"""Order-book walking simulator for Polymarket Phase A paper fills.

Given a list of CLOB asks (`{"price": float, "size": float}` per level) and
a USDC budget, walk levels cheapest-first until the budget is spent or asks
are exhausted. Returns a dict with VWAP, contracts acquired, slippage in
percentage points, and an estimated 2% resolution fee on the win-side payout.

This is the Phase A bridge between a `PolymarketDecision` and a real-world
P&L estimate. It does NOT place orders. It does NOT touch a wallet. It is
deterministic and testable.
"""

from __future__ import annotations

from typing import Any, Iterable


def simulate_fill(
    asks: Iterable[dict[str, float]],
    budget_usd: float,
    fee_rate: float = 0.02,
) -> dict[str, Any]:
    """Walk asks cheapest-first, accumulating fills until budget is spent.

    Args:
        asks: order book asks, each `{"price": float in [0,1], "size": float contracts}`.
            May be unsorted; this function sorts ascending by price.
        budget_usd: USDC budget to spend.
        fee_rate: Polymarket charges 2% on winning resolutions by default.

    Returns:
        A dict with:
          - filled (bool): True if any contracts were acquired.
          - filled_usd (float): USDC actually spent.
          - contracts (float): contracts acquired.
          - vwap (float): volume-weighted average fill price (0.0 if nothing filled).
          - remaining_budget (float): USDC unspent.
          - levels_consumed (int): how many price levels were touched.
          - slippage_pp (float): (vwap - best_ask) * 100, percentage points of slippage.
          - fee_estimate_if_win (float): contracts * 1.0 * fee_rate.
            Polymarket fees only apply on winning resolutions; this is the
            cost the winning side will pay if the position resolves favourably.
          - fills (list): per-level breakdown.
    """
    sorted_asks = sorted(asks, key=lambda x: float(x["price"]))
    fills: list[dict[str, float]] = []
    remaining = float(budget_usd)
    contracts = 0.0
    best_ask: float | None = None

    for level in sorted_asks:
        if remaining <= 0:
            break
        price = float(level["price"])
        avail_size = float(level["size"])
        if best_ask is None:
            best_ask = price
        avail_usd = price * avail_size
        spend = min(remaining, avail_usd)
        if spend <= 0 or price <= 0:
            continue
        size_taken = spend / price
        fills.append({"price": price, "size": size_taken, "usd": spend})
        contracts += size_taken
        remaining -= spend

    filled_usd = float(budget_usd) - remaining
    vwap = filled_usd / contracts if contracts > 0 else 0.0
    slippage_pp = (vwap - best_ask) * 100 if best_ask is not None and contracts > 0 else 0.0
    fee_estimate_if_win = contracts * 1.0 * fee_rate

    return {
        "filled": filled_usd > 0,
        "filled_usd": round(filled_usd, 6),
        "contracts": round(contracts, 6),
        "vwap": round(vwap, 6),
        "remaining_budget": round(remaining, 6),
        "levels_consumed": len(fills),
        "slippage_pp": round(slippage_pp, 4),
        "fee_estimate_if_win": round(fee_estimate_if_win, 6),
    }


def is_economic_when_correct(fill: dict[str, Any]) -> bool:
    """Return True if the position pays out positive even when correct.

    On Polymarket each contract pays $1.00 on a winning resolution, with
    a 2% fee on the winning side. A position bought at vwap ~0.99 pays
    only ~$0.01/contract above the buy price; if that's less than the
    fee, the position loses money even when the prediction is right.

    This guard catches the "BUY_NO at 99c on a near-zero YES market"
    failure mode observed live: contract pays $1, fee is $0.02, but
    you paid $0.999. Net = -$0.019/contract no matter the outcome.

    Args:
        fill: dict from simulate_fill. Reads contracts, filled_usd,
            fee_estimate_if_win.

    Returns False on unfilled positions (contracts=0) and on positions
    where the win-side payout doesn't cover entry + fee.
    """
    contracts = float(fill.get("contracts", 0))
    filled_usd = float(fill.get("filled_usd", 0))
    fee_if_win = float(fill.get("fee_estimate_if_win", 0))
    if contracts <= 0 or filled_usd <= 0:
        return False
    win_payout = contracts * 1.0
    return (win_payout - filled_usd - fee_if_win) > 0
