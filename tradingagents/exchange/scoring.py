"""Score paper fills against Polymarket resolution outcomes.

Two pure functions:
  - classify_outcome(closed, outcome_prices) -> (MarketOutcome, current_yes_price)
    Reads the gamma `/markets` response fields and decides whether the market
    has resolved YES/NO/50-50, is still trading, or is in the UMA dispute window.
  - score_position(fill, outcome, current_yes_price) -> dict
    Computes realized P&L for resolved outcomes and mark-to-market P&L for
    pending positions.

Deterministic, no I/O. The CLI in scripts/score_fills.py wraps these with
gamma fetches and JSONL aggregation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class MarketOutcome(str, Enum):
    PENDING = "PENDING"          # market still open
    YES_WINS = "YES_WINS"        # outcomePrices ~ [1, 0]
    NO_WINS = "NO_WINS"          # outcomePrices ~ [0, 1]
    CANCELED = "CANCELED"        # outcomePrices ~ [0.5, 0.5]
    UNKNOWN = "UNKNOWN"          # closed but neither cleanly resolved nor 50-50


# Tolerance bands for resolution detection. Polymarket settles to exactly 1/0
# in normal flow but legacy markets sometimes show very-close-to-1 floats.
_RESOLVED_HI = 0.99
_RESOLVED_LO = 0.01
_CANCEL_LO = 0.49
_CANCEL_HI = 0.51


def classify_outcome(
    closed: bool,
    outcome_prices: list[float] | None,
) -> tuple[MarketOutcome, float | None]:
    """Decide the market's resolution state from gamma fields.

    Args:
        closed: gamma `closed` boolean.
        outcome_prices: gamma `outcomePrices` already parsed to floats [yes, no].

    Returns:
        (outcome, current_yes_price). current_yes_price is set only for PENDING
        markets and is the live YES price for MTM calculations.
    """
    if not outcome_prices or len(outcome_prices) < 2:
        return (MarketOutcome.UNKNOWN, None)

    yes, no = float(outcome_prices[0]), float(outcome_prices[1])

    if not closed:
        return (MarketOutcome.PENDING, yes)

    # Closed market - determine resolution
    if yes >= _RESOLVED_HI and no <= _RESOLVED_LO:
        return (MarketOutcome.YES_WINS, None)
    if no >= _RESOLVED_HI and yes <= _RESOLVED_LO:
        return (MarketOutcome.NO_WINS, None)
    if _CANCEL_LO <= yes <= _CANCEL_HI and _CANCEL_LO <= no <= _CANCEL_HI:
        return (MarketOutcome.CANCELED, None)
    # Closed but unclean: dispute window, legacy [0,0] data, or other anomaly
    return (MarketOutcome.UNKNOWN, None)


def score_position(
    fill: dict[str, Any],
    outcome: MarketOutcome,
    current_yes_price: float | None,
) -> dict[str, Any]:
    """Compute P&L for one paper-fill position.

    Args:
        fill: dict with at least `direction` (BUY_YES|BUY_NO), `contracts`,
            `filled_usd`, `fee_estimate_if_win`.
        outcome: from classify_outcome.
        current_yes_price: live YES price for MTM (PENDING only).

    Returns dict with:
        status: RESOLVED_WIN | RESOLVED_LOSS | CANCELED | PENDING | UNRESOLVED
        payout_usd: USDC payout received (0 for losses, contract value for wins)
        fee_paid: fee actually paid (only on winning resolves)
        pnl_usd: realized P&L (RESOLVED/CANCELED) or 0.0 otherwise
        roi: pnl_usd / filled_usd (or None if filled_usd is 0)
        mtm_value_usd: PENDING only, current market value of the position
        mtm_pnl_usd: PENDING only, mtm_value_usd - filled_usd
    """
    direction = fill["direction"]
    contracts = float(fill["contracts"])
    filled_usd = float(fill["filled_usd"])
    fee_if_win = float(fill.get("fee_estimate_if_win", 0.0))

    base = {
        "status": "UNRESOLVED",
        "payout_usd": 0.0,
        "fee_paid": 0.0,
        "pnl_usd": 0.0,
        "roi": None,
        "mtm_value_usd": None,
        "mtm_pnl_usd": None,
    }

    if outcome == MarketOutcome.UNKNOWN:
        return base

    if outcome == MarketOutcome.PENDING:
        if current_yes_price is None:
            return base
        if direction == "BUY_YES":
            mtm_value = contracts * current_yes_price
        else:  # BUY_NO
            mtm_value = contracts * (1.0 - current_yes_price)
        return {
            **base,
            "status": "PENDING",
            "mtm_value_usd": round(mtm_value, 6),
            "mtm_pnl_usd": round(mtm_value - filled_usd, 6),
        }

    if outcome == MarketOutcome.CANCELED:
        # 50-50 refund: each contract returns $0.50, no fee charged
        payout = contracts * 0.5
        pnl = payout - filled_usd
        return {
            **base,
            "status": "CANCELED",
            "payout_usd": round(payout, 6),
            "fee_paid": 0.0,
            "pnl_usd": round(pnl, 6),
            "roi": round(pnl / filled_usd, 6) if filled_usd > 0 else None,
        }

    # YES_WINS or NO_WINS: did the position win?
    is_win = (
        (direction == "BUY_YES" and outcome == MarketOutcome.YES_WINS)
        or (direction == "BUY_NO" and outcome == MarketOutcome.NO_WINS)
    )

    if is_win:
        payout = contracts * 1.0
        pnl = payout - fee_if_win - filled_usd
        return {
            **base,
            "status": "RESOLVED_WIN",
            "payout_usd": round(payout, 6),
            "fee_paid": round(fee_if_win, 6),
            "pnl_usd": round(pnl, 6),
            "roi": round(pnl / filled_usd, 6) if filled_usd > 0 else None,
        }

    # Loss: position is worthless
    return {
        **base,
        "status": "RESOLVED_LOSS",
        "payout_usd": 0.0,
        "fee_paid": 0.0,
        "pnl_usd": round(-filled_usd, 6),
        "roi": -1.0 if filled_usd > 0 else None,
    }
