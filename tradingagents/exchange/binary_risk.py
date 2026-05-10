"""Kelly criterion position sizing for Polymarket binary contracts.

YES/NO contracts resolve at $1 or $0. The existing stop-loss-based formula
(RISK_PER_TRADE_PCT / stop_loss_pct) produces nonsense for binary outcomes
because there is no stop-loss price level to set.

Kelly criterion: f* = (b*p - q) / b
  p = probability of winning (= decision.confidence)
  q = 1 - p
  b = net odds (payout per unit risked)
    BUY_YES: b = (1 / yes_price) - 1
    BUY_NO:  b = (1 / (1 - yes_price)) - 1

A half-Kelly multiplier (default 0.5) is applied to reduce variance in
practice. The result is capped at max_fraction (default 20%) per trade.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PolymarketDecision, PolymarketDirection

DEFAULT_MAX_FRACTION: float = 0.20
DEFAULT_KELLY_MULTIPLIER: float = 0.50
DEFAULT_MIN_CONFIDENCE: float = 0.55


def kelly_fraction(p: float, b: float) -> float:
    """Core Kelly formula: f* = (b*p - q) / b.

    Args:
        p: probability of winning (0.0–1.0)
        b: net odds — payout per unit risked (e.g. 1.5 → win $1.50 per $1 bet)

    Returns:
        Optimal fraction of capital to bet. Negative means negative EV — don't bet.
    """
    q = 1.0 - p
    return (b * p - q) / b


def _net_odds(decision: PolymarketDecision) -> float:
    """Net odds b for the direction in decision."""
    yes_price = decision.yes_price_at_analysis
    if decision.direction == PolymarketDirection.BUY_YES:
        return (1.0 / yes_price) - 1.0
    # BUY_NO: bet on the NO contract priced at (1 - yes_price)
    no_price = 1.0 - yes_price
    return (1.0 / no_price) - 1.0


def size_order(
    decision: PolymarketDecision,
    capital_usd: float,
    *,
    max_fraction: float = DEFAULT_MAX_FRACTION,
    kelly_multiplier: float = DEFAULT_KELLY_MULTIPLIER,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> dict[str, float | str]:
    """Compute Kelly-optimal position size for a Polymarket binary contract.

    Args:
        decision: PolymarketDecision from the research engine.
        capital_usd: total available capital in USD.
        max_fraction: hard cap on fraction of capital per trade (default 0.20).
        kelly_multiplier: fraction of full Kelly to use; 0.5 = half-Kelly (default).
        min_confidence: minimum confidence to place any bet (default 0.55).

    Returns dict with:
        fraction: fraction of capital to bet (0.0 if no bet).
        usd: dollar amount to bet (fraction * capital_usd).
        reason: human-readable explanation of the sizing decision.
    """
    zero: dict[str, float | str] = {"fraction": 0.0, "usd": 0.0}

    if decision.direction == PolymarketDirection.HOLD:
        return {**zero, "reason": "HOLD — no position to size"}

    if decision.confidence < min_confidence:
        return {
            **zero,
            "reason": (
                f"confidence {decision.confidence:.2f} below minimum "
                f"{min_confidence:.2f} — no bet"
            ),
        }

    b = _net_odds(decision)
    f_full = kelly_fraction(p=decision.confidence, b=b)

    if f_full <= 0:
        return {
            **zero,
            "reason": (
                f"negative Kelly fraction ({f_full:.4f}) — negative expected value "
                f"at confidence={decision.confidence:.2f}, "
                f"price={decision.yes_price_at_analysis:.2f}"
            ),
        }

    f_adjusted = f_full * kelly_multiplier
    capped = f_adjusted > max_fraction
    f_final = min(f_adjusted, max_fraction)

    reason = (
        f"Kelly f*={f_full:.4f}, {kelly_multiplier}x multiplier → {f_adjusted:.4f}"
        + (f", capped at max_fraction={max_fraction:.2f}" if capped else "")
    )
    return {
        "fraction": f_final,
        "usd": round(f_final * capital_usd, 2),
        "reason": reason,
    }
