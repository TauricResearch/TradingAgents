"""Package deterministic analytics outputs as MetricReadings for agents.

The quant/risk engines return plain numbers; evidence agents consume named
MetricReadings. This module is the (tested) glue: it decides the canonical
metric names that roster specs select on.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from tradingagents.contracts import (
    MarketSnapshot,
    MetricReading,
    OHLCVBar,
    RiskLimits,
    Timeframe,
)
from tradingagents.pro.analytics import (
    atr_stop_loss,
    atr_take_profits,
    close_zscore,
    fixed_risk_position_size,
    historical_cvar,
    historical_var,
    invalidation_stop_loss,
    kelly_fraction,
    realized_volatility,
    trend_slope,
)

QUANT_SOURCE = "quant_engine"
RISK_SOURCE = "risk_engine"

# Bars per trading day, for scaling per-bar risk to the daily horizon that
# RiskLimits speaks (review finding QUANT-02). W1 scales down (a weekly bar
# spans ~5 trading days).
BARS_PER_DAY: dict[Timeframe, float] = {
    Timeframe.M1: 1440, Timeframe.M5: 288, Timeframe.M15: 96, Timeframe.M30: 48,
    Timeframe.H1: 24, Timeframe.H4: 6, Timeframe.D1: 1, Timeframe.W1: 1 / 5,
}


def infer_timeframe(snapshot: MarketSnapshot) -> Timeframe:
    return snapshot.bars[-1].timeframe if snapshot.bars else Timeframe.D1


def _reading(name: str, value: float, source: str, unit: str | None = None) -> MetricReading:
    return MetricReading(name=name, value=value, unit=unit, source=source)


def compute_quant_metrics(bars: Sequence[OHLCVBar]) -> dict[str, MetricReading]:
    """Quant features for the quant team; skips features lacking history."""
    out: dict[str, MetricReading] = {}
    if len(bars) >= 3:
        vol = realized_volatility(bars)
        slope_pct, r_squared = trend_slope(bars)
        out["REALIZED_VOL_ANN"] = _reading("REALIZED_VOL_ANN", vol, QUANT_SOURCE, "annualized")
        out["TREND_SLOPE_PCT"] = _reading("TREND_SLOPE_PCT", slope_pct, QUANT_SOURCE, "%/bar")
        out["TREND_R2"] = _reading("TREND_R2", r_squared, QUANT_SOURCE, "r_squared")
    if len(bars) >= 50:
        out["CLOSE_ZSCORE_50"] = _reading(
            "CLOSE_ZSCORE_50", close_zscore(bars, 50), QUANT_SOURCE, "sigma"
        )
    return out


def _simple_returns(bars: Sequence[OHLCVBar]) -> list[float]:
    closes = [b.close for b in bars]
    return [(b - a) / a for a, b in zip(closes, closes[1:], strict=False)]


def compute_risk_metrics(
    snapshot: MarketSnapshot,
    limits: RiskLimits,
    equity: float,
    side: str = "BUY",
    timeframe: Timeframe | None = None,
    win_rate: float | None = None,
    avg_win: float | None = None,
    avg_loss: float | None = None,
    invalidation_price: float | None = None,
) -> dict[str, MetricReading]:
    """Risk-engine outputs for the risk team, from current snapshot state.

    Entry is the latest close; the take-profit ladder is ATR-scaled. The
    stop is ATR-scaled by default, but when ``invalidation_price`` is
    supplied (the reflection stage's structured thesis-death level) the stop
    derives from it instead — the trade must not outlive its own thesis.
    A wrong-sided invalidation falls back to the ATR stop rather than
    blocking the run. Kelly appears only when historical win statistics are
    supplied (they come from the memory layer in Phase 5; absent stats must
    not fabricate a Kelly). VaR/CVaR need >= 21 bars of returns.
    """
    out: dict[str, MetricReading] = {
        "MAX_RISK_PER_TRADE_PCT": _reading(
            "MAX_RISK_PER_TRADE_PCT", limits.max_risk_per_trade_pct, RISK_SOURCE, "%"
        ),
        "MAX_POSITION_PCT": _reading(
            "MAX_POSITION_PCT", limits.max_position_pct_equity, RISK_SOURCE, "%"
        ),
        "MAX_LEVERAGE": _reading("MAX_LEVERAGE", limits.max_leverage, RISK_SOURCE, "x"),
        "MAX_DRAWDOWN_PCT": _reading(
            "MAX_DRAWDOWN_PCT", limits.max_drawdown_pct, RISK_SOURCE, "%"
        ),
    }

    timeframe = timeframe or infer_timeframe(snapshot)
    bars = [b for b in snapshot.bars if b.timeframe == timeframe]
    if len(bars) >= 21:
        returns = _simple_returns(bars)
        # scale per-bar VaR/CVaR to the daily horizon RiskLimits speaks
        # (sqrt-time under iid returns; documented approximation)
        scale = math.sqrt(BARS_PER_DAY[timeframe])
        out["VAR_95"] = _reading("VAR_95", historical_var(returns, 0.95) * scale,
                                 RISK_SOURCE, "fraction/day")
        out["CVAR_95"] = _reading("CVAR_95", historical_cvar(returns, 0.95) * scale,
                                  RISK_SOURCE, "fraction/day")

    atr_reading = snapshot.get_indicator("ATR_14", timeframe)
    if bars and atr_reading is not None:
        entry = bars[-1].close
        atr = atr_reading.value["value"]
        if atr > 0 and not math.isnan(atr):
            stop = atr_stop_loss(entry, atr, side)
            if invalidation_price is not None:
                try:
                    stop = invalidation_stop_loss(entry, invalidation_price, atr, side)
                    out["INVALIDATION_PRICE"] = _reading(
                        "INVALIDATION_PRICE", invalidation_price, RISK_SOURCE
                    )
                except ValueError:
                    pass  # wrong-sided/unusable level: keep the ATR stop
            out["ENTRY_REF_PRICE"] = _reading("ENTRY_REF_PRICE", entry, RISK_SOURCE)
            out["ATR_STOP"] = _reading("ATR_STOP", stop, RISK_SOURCE)
            for i, tp in enumerate(atr_take_profits(entry, atr, side), start=1):
                out[f"ATR_TP{i}"] = _reading(f"ATR_TP{i}", tp.price, RISK_SOURCE)
            size = fixed_risk_position_size(
                equity,
                limits.max_risk_per_trade_pct,
                entry,
                stop,
                max_position_pct=limits.max_position_pct_equity,
            )
            out["POSITION_SIZE_UNITS"] = _reading(
                "POSITION_SIZE_UNITS", size.quantity, RISK_SOURCE, "units"
            )
            out["POSITION_NOTIONAL"] = _reading(
                "POSITION_NOTIONAL", size.notional or 0.0, RISK_SOURCE, "quote_ccy"
            )
            out["POSITION_PCT_EQUITY"] = _reading(
                "POSITION_PCT_EQUITY", size.pct_of_equity or 0.0, RISK_SOURCE, "%"
            )

    if win_rate is not None and avg_win is not None and avg_loss is not None:
        out["KELLY_FRACTION"] = _reading(
            "KELLY_FRACTION", kelly_fraction(win_rate, avg_win, avg_loss), RISK_SOURCE,
            "fraction"
        )
    return out


def compute_neutral_risk_metrics(
    snapshot: MarketSnapshot,
    limits: RiskLimits,
    equity: float,
    timeframe: Timeframe | None = None,
    win_rate: float | None = None,
    avg_win: float | None = None,
    avg_loss: float | None = None,
) -> dict[str, MetricReading]:
    """Direction-neutral risk metrics for the *pre-decision* stage.

    The eval runs exposed a phantom directional vote: computing the ATR
    ladder for a default BUY side made the dynamic stop/target agents emit
    'bullish' evidence on any tape. Before a direction exists, levels are
    published for BOTH hypothetical sides (LONG_*/SHORT_*); sizing is
    side-symmetric (|entry - stop| is the same distance either way). The
    portfolio manager still computes the single-sided set after the judge
    rules."""
    timeframe = timeframe or infer_timeframe(snapshot)
    out = compute_risk_metrics(
        snapshot, limits, equity, side="BUY", timeframe=timeframe,
        win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss,
    )
    # re-label the BUY-sided levels as LONG_*, add SHORT_* mirrors
    for name in [n for n in out if n.startswith(("ATR_STOP", "ATR_TP"))]:
        reading = out.pop(name)
        out[f"{name}_LONG"] = _reading(f"{name}_LONG", reading.value, RISK_SOURCE)
    atr_reading = snapshot.get_indicator("ATR_14", timeframe)
    entry = out.get("ENTRY_REF_PRICE")
    if atr_reading is not None and entry is not None:
        atr = atr_reading.value["value"]
        if atr > 0 and not math.isnan(atr):
            out["ATR_STOP_SHORT"] = _reading(
                "ATR_STOP_SHORT", atr_stop_loss(entry.value, atr, "SELL"), RISK_SOURCE
            )
            for i, tp in enumerate(atr_take_profits(entry.value, atr, "SELL"), start=1):
                out[f"ATR_TP{i}_SHORT"] = _reading(
                    f"ATR_TP{i}_SHORT", tp.price, RISK_SOURCE
                )
    return out
