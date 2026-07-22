"""Deterministic risk engine (Constraint 2: code produces the numbers).

Risk-team agents receive these outputs as pre-computed MetricReadings and
explain them; nothing here is ever delegated to an LLM. The Phase 4 risk
gate and Phase 9 execution layer call the same functions.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from tradingagents.contracts import PositionSize, TakeProfitLevel

# cap-bound sizes leave headroom (review R2.8): sizing uses sizing-time
# equity while the execution validator re-checks against LIVE equity — a
# size sitting exactly on the cap bounced on every ordinary equity dip
# (observed in production: "notional 10000.00 exceeds cap 9991.35", every
# at-cap order rejected, the paper track record silently frozen). The
# validator stays strict; the size steps back from the boundary instead.
NOTIONAL_CAP_HEADROOM = 0.99


def fixed_risk_position_size(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
    max_position_pct: float = 100.0,
) -> PositionSize:
    """Size so that (entry -> stop) loses exactly ``risk_pct`` of equity,
    capped by ``max_position_pct`` of equity notional (less a drift
    headroom when the cap binds)."""
    if equity <= 0:
        raise ValueError("equity must be positive")
    if not 0 < risk_pct <= 100:
        raise ValueError("risk_pct must be in (0, 100]")
    per_unit_risk = abs(entry - stop)
    if per_unit_risk == 0:
        raise ValueError("entry and stop cannot be equal")
    quantity = (equity * risk_pct / 100.0) / per_unit_risk
    notional_cap = equity * max_position_pct / 100.0
    # >= — a size landing EXACTLY on the cap needs the drift headroom too
    # (10% of a clean 100k == the cap; the strict > let it through at the
    # boundary and the validator bounced it on the first equity dip)
    if quantity * entry >= notional_cap:
        quantity = notional_cap * NOTIONAL_CAP_HEADROOM / entry
    notional = quantity * entry
    return PositionSize(
        quantity=quantity,
        notional=notional,
        pct_of_equity=min(notional / equity * 100.0, 100.0),
    )


def kelly_fraction(
    win_rate: float, avg_win: float, avg_loss: float, cap: float = 0.25
) -> float:
    """Kelly criterion fraction, capped (fractional Kelly is house policy).

    f* = w - (1 - w) / (avg_win / avg_loss). Negative edges return 0.0 —
    the correct bet on a losing proposition is nothing.
    """
    if not 0 <= win_rate <= 1:
        raise ValueError("win_rate must be in [0, 1]")
    if avg_win <= 0 or avg_loss <= 0:
        raise ValueError("avg_win and avg_loss must be positive magnitudes")
    if not 0 < cap <= 1:
        raise ValueError("cap must be in (0, 1]")
    payoff = avg_win / avg_loss
    fraction = win_rate - (1 - win_rate) / payoff
    return max(0.0, min(fraction, cap))


def historical_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Historical Value-at-Risk as a positive loss fraction.

    Empirical quantile (linear interpolation) of the return distribution:
    VaR(95%) = 0.021 means "worst 5% of periods lost at least 2.1%".
    """
    if not 0.5 <= confidence < 1:
        raise ValueError("confidence must be in [0.5, 1)")
    if len(returns) < 20:
        raise ValueError(f"need >= 20 return observations, got {len(returns)}")
    ordered = sorted(returns)
    position = (1 - confidence) * (len(ordered) - 1)
    lower = math.floor(position)
    weight = position - lower
    upper = min(lower + 1, len(ordered) - 1)
    quantile = ordered[lower] * (1 - weight) + ordered[upper] * weight
    return max(0.0, -quantile)


def historical_cvar(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Expected shortfall: mean loss of the tail at/beyond the VaR quantile."""
    var = historical_var(returns, confidence)
    tail = [r for r in returns if -r >= var]
    if not tail:
        return var
    return -math.fsum(tail) / len(tail)


def atr_stop_loss(entry: float, atr: float, side: str, multiple: float = 2.0) -> float:
    """Volatility-scaled stop: ``multiple`` ATRs against the position."""
    if entry <= 0 or atr <= 0 or multiple <= 0:
        raise ValueError("entry, atr, and multiple must be positive")
    if side == "BUY":
        return entry - multiple * atr
    if side == "SELL":
        return entry + multiple * atr
    raise ValueError(f"side must be BUY or SELL, got {side!r}")


def invalidation_stop_loss(
    entry: float,
    invalidation: float,
    atr: float,
    side: str,
    buffer_multiple: float = 0.25,
) -> float:
    """Stop derived from the thesis-invalidation level, not a template.

    The trade must die where its thesis dies: the stop sits just beyond the
    invalidation price by a small ATR buffer (noise allowance), capped so the
    overshoot never exceeds the contract bound TradeRecommendation enforces
    (max of 25% of the entry->invalidation distance and 0.1% of entry).
    Raises ValueError when the invalidation lies on the wrong side of entry
    for the position — callers treat that as "no usable level" and fall back
    to the ATR stop.
    """
    if entry <= 0 or invalidation <= 0 or atr <= 0:
        raise ValueError("entry, invalidation, and atr must be positive")
    if buffer_multiple <= 0:
        raise ValueError("buffer_multiple must be positive")
    if side == "BUY":
        if not invalidation < entry:
            raise ValueError("BUY invalidation must sit below entry")
    elif side == "SELL":
        if not invalidation > entry:
            raise ValueError("SELL invalidation must sit above entry")
    else:
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    distance = abs(entry - invalidation)
    overshoot_cap = max(0.25 * distance, 0.001 * entry)
    buffer = min(buffer_multiple * atr, overshoot_cap)
    return invalidation - buffer if side == "BUY" else invalidation + buffer


def take_profits_from_risk(
    entry: float,
    stop: float,
    side: str,
    r_multiples: Sequence[float] = (0.5, 3.5),
    fractions: Sequence[float] = (0.5, 0.5),
) -> list[TakeProfitLevel]:
    """R-based take-profit ladder: rungs at multiples of the ACTUAL
    entry→stop risk, not raw ATR — so a tighter invalidation-derived stop
    keeps the same reward geometry. Defaults (0.5R for half, 3.5R for half)
    give a size-weighted planned R:R of exactly 2.0 and a structural ~67%
    hit rate (see RiskLimits.tp_r_multiples).
    """
    if entry <= 0:
        raise ValueError("entry must be positive")
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("entry and stop cannot be equal")
    if (list(r_multiples) != sorted(r_multiples)
            or len(set(r_multiples)) != len(r_multiples)
            or any(m <= 0 for m in r_multiples)):
        raise ValueError("r_multiples must be positive and strictly ascending")
    if len(fractions) != len(r_multiples):
        raise ValueError("fractions and r_multiples must have equal length")
    sign = 1 if side == "BUY" else -1
    multiples = list(r_multiples)
    if side == "SELL":
        # a deep-R short target can cross zero when the stop distance is a
        # large fraction of price; scale the ladder to keep targets positive
        # (proportions preserved — the quality gate rejects the trade if the
        # squeezed R:R drops below the configured minimum, which is correct
        # for such degenerate geometry)
        deepest = entry - multiples[-1] * risk
        if deepest <= 0:
            scale = 0.95 * entry / (multiples[-1] * risk)
            multiples = [m * scale for m in multiples]
    return [
        TakeProfitLevel(price=entry + sign * m * risk, size_fraction=f)
        for m, f in zip(multiples, fractions, strict=True)
    ]


def atr_take_profits(
    entry: float,
    atr: float,
    side: str,
    multiples: Sequence[float] = (2.0, 4.0),
    fractions: Sequence[float] | None = None,
) -> list[TakeProfitLevel]:
    """ATR-multiple take-profit ladder; fractions default to equal split."""
    if entry <= 0 or atr <= 0:
        raise ValueError("entry and atr must be positive")
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    if list(multiples) != sorted(multiples) or len(set(multiples)) != len(multiples):
        raise ValueError("multiples must be strictly ascending")
    if fractions is None:
        fractions = [1.0 / len(multiples)] * len(multiples)
    if len(fractions) != len(multiples):
        raise ValueError("fractions and multiples must have equal length")
    sign = 1 if side == "BUY" else -1
    return [
        TakeProfitLevel(price=entry + sign * m * atr, size_fraction=f)
        for m, f in zip(multiples, fractions, strict=True)
    ]
