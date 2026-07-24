"""Execution-cost models: slippage, commission, liquidity participation.

Deterministic and side-aware: buys fill above the reference price, sells
below. The participation cap is the liquidity constraint — an order may
not exceed a fraction of the bar's traded volume; the remainder is
dropped, never magically filled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SlippageModel:
    """Side-aware execution slippage against the trader. Total adverse move =
    a fixed ``bps`` + a half-spread (``spread_bps``) + a square-root MARKET
    IMPACT term ``impact_bps * sqrt(participation)`` (roadmap P4 / track T5 —
    the standard model: cost per share grows with order size relative to the
    bar's liquidity). ``spread_bps``/``impact_bps`` default 0, so a model with
    only ``bps`` is byte-identical to before."""

    bps: float = 2.0            # fixed basis points of the reference price
    spread_bps: float = 0.0     # half the quoted bid/ask spread, paid each side
    impact_bps: float = 0.0     # coefficient on sqrt(participation) impact

    def fill_price(self, reference: float, side: str) -> float:
        """Fixed-cost fill (no size impact) — the zero-participation case."""
        return self.fill_price_at(reference, side, 0.0)

    def fill_price_at(self, reference: float, side: str,
                      participation: float = 0.0) -> float:
        """Fill price including market impact for an order taking
        ``participation`` (order size / bar volume) of the bar's liquidity."""
        if reference <= 0:
            raise ValueError("reference price must be positive")
        adverse = (self.bps + self.spread_bps
                   + self.impact_bps * math.sqrt(max(0.0, participation)))
        if side == "BUY":
            return reference * (1 + adverse / 10_000)
        if side == "SELL":
            return reference * (1 - adverse / 10_000)
        raise ValueError(f"side must be BUY or SELL, got {side!r}")


@dataclass(frozen=True)
class CommissionModel:
    rate_bps: float = 1.0  # of traded notional, charged per fill
    minimum: float = 0.0

    def cost(self, quantity: float, price: float) -> float:
        if quantity < 0 or price <= 0:
            raise ValueError("quantity must be >= 0 and price > 0")
        return max(quantity * price * self.rate_bps / 10_000, self.minimum if quantity else 0.0)


@dataclass(frozen=True)
class LiquidityModel:
    max_participation: float = 0.1  # fraction of the fill bar's volume

    def cap_quantity(self, desired: float, bar_volume: float) -> float:
        if not 0 < self.max_participation <= 1:
            raise ValueError("max_participation must be in (0, 1]")
        if desired < 0:
            raise ValueError("desired quantity must be >= 0")
        return min(desired, self.max_participation * bar_volume)


# --- per-asset cost profiles (roadmap P4 / track T5) ------------------------
#
# CONSERVATIVE MODELLING ASSUMPTIONS, not measured venue data — calibrate to
# your own broker/exchange before trusting absolute net returns. The point is
# that costs are asset-specific: a gold-spot fill is cheaper than an alt-coin
# fill, and a size-taking order pays square-root impact on top. Values are
# (slippage_bps, spread_bps, impact_bps, commission_bps); every asset keeps the
# default 10%-of-bar participation cap.
_COST_PROFILES: dict[str, tuple[float, float, float, float]] = {
    # asset name       slip  spread  impact  commission
    "GOLD":           (1.0,  0.5,    5.0,    0.5),
    "BITCOIN":        (1.0,  1.0,    8.0,    7.0),
    "ETHEREUM":       (1.5,  1.5,   10.0,    7.0),
    "SOLANA":         (3.0,  3.0,   15.0,    7.0),
}
_DEFAULT_PROFILE = (2.0, 1.0, 10.0, 7.0)  # unknown asset → a cautious crypto-ish default


@dataclass(frozen=True)
class FundingModel:
    """Perpetual-swap funding accrual (roadmap P4 / track T5). Perps have no
    expiry; instead longs and shorts exchange a periodic funding payment.
    ``annual_rate_pct`` is the ASSUMED average funding (positive → longs pay
    shorts, the usual state in a bull market); accrual is continuous in elapsed
    hours — a smooth approximation of the discrete 8h ticks, deterministic and
    order-independent. Opt-in: only relevant when backtesting a perp, never a
    spot instrument."""

    annual_rate_pct: float = 0.0

    def cash_delta(self, notional: float, side: str, hours: float) -> float:
        """Signed cash change for holding ``notional`` on ``side`` for
        ``hours``. Longs pay (negative) when the rate is positive; shorts
        receive (positive), and vice-versa."""
        if notional < 0 or hours < 0:
            raise ValueError("notional and hours must be >= 0")
        pay = notional * (self.annual_rate_pct / 100.0) * (hours / (365 * 24))
        return -pay if side == "BUY" else pay


@dataclass(frozen=True)
class MarginModel:
    """Leverage + maintenance-margin + forced-liquidation (roadmap P4 / track
    T5). ``leverage`` lifts the broker's gross-exposure cap (initial margin =
    notional / leverage); ``maintenance_margin_pct`` is the equity floor below
    which open positions are force-liquidated; ``liquidation_penalty_bps`` is
    the extra adverse slippage a forced close pays. Opt-in: the neutral
    setting (``leverage=1, maintenance_margin_pct=0``) is byte-identical to no
    margin model at all — no cap change, no liquidation."""

    leverage: float = 1.0
    maintenance_margin_pct: float = 0.0
    liquidation_penalty_bps: float = 0.0

    def __post_init__(self) -> None:
        if self.leverage <= 0:
            raise ValueError("leverage must be > 0")
        if not 0 <= self.maintenance_margin_pct < 100:
            raise ValueError("maintenance_margin_pct must be in [0, 100)")

    @property
    def is_neutral(self) -> bool:
        """True when the model changes nothing vs. having no margin model."""
        return (self.leverage <= 1.0 and self.maintenance_margin_pct <= 0.0
                and self.liquidation_penalty_bps <= 0.0)


def cost_profile_for(asset) -> tuple[SlippageModel, CommissionModel, LiquidityModel]:
    """Return (slippage, commission, liquidity) models tuned per asset class.
    ``asset`` may be an ``AssetClass`` or its name. See ``_COST_PROFILES`` for
    the (assumed, conservative) parameters."""
    name = getattr(asset, "name", str(asset)).upper()
    slip, spread, impact, commission = _COST_PROFILES.get(name, _DEFAULT_PROFILE)
    return (
        SlippageModel(bps=slip, spread_bps=spread, impact_bps=impact),
        CommissionModel(rate_bps=commission),
        LiquidityModel(),
    )
