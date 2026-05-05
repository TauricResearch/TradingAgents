from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_trade_filter(
    *,
    trade_levels: Dict[str, Any] | None,
    rating: str,
    rm_rating: str | None,
    trader_action: str | None,
    data_quality: str,
    error_count: int,
    structured_valid: bool,
    threshold: float = 0.65,
    rr_hard_min: float = 1.3,
    atr_pct_hard_max: float = 0.08,
) -> Dict[str, Any]:
    reasons: List[str] = []
    hard_reject_reasons: List[str] = []

    if not trade_levels:
        hard_reject_reasons.append("Missing trade_levels output; cannot validate execution setup.")
        return {
            "filtered_out": True,
            "hard_reject": True,
            "signal_quality": 0.2,
            "market_quality": 0.2,
            "execution_quality": 0.2,
            "score": 0.2,
            "pass": False,
            "threshold": float(threshold),
            "reasons": reasons,
            "hard_reject_reasons": hard_reject_reasons,
        }

    regime = str(trade_levels.get("regime", "unknown"))
    regime_conf = float(trade_levels.get("regime_confidence", 0.0) or 0.0)
    bias = str(trade_levels.get("bias", "neutral"))
    anchors = trade_levels.get("anchors") or {}
    atr_pct = float(anchors.get("atr_pct", 0.0) or 0.0)
    trend_strength = float(anchors.get("trend_strength", 0.0) or 0.0)

    rr_target = float(trade_levels.get("rr_target", 0.0) or 0.0)
    entry_price = float(trade_levels.get("entry_price", 0.0) or 0.0)
    stop_loss = trade_levels.get("stop_loss")
    stop_distance_pct = 0.0
    if entry_price and stop_loss is not None:
        stop_distance_pct = abs(float(entry_price) - float(stop_loss)) / float(entry_price)

    entry_condition = str(trade_levels.get("entry_condition", "")).lower()
    uses_breakout_language = any(k in entry_condition for k in ("breakout", "close above", "close below"))

    if rr_target and rr_target < rr_hard_min:
        hard_reject_reasons.append(f"RR target too low ({rr_target:.2f} < {rr_hard_min:.2f}).")
    if data_quality == "low":
        hard_reject_reasons.append("Data quality is low.")
    if atr_pct and atr_pct > atr_pct_hard_max:
        hard_reject_reasons.append(f"ATR% too high ({atr_pct:.3f} > {atr_pct_hard_max:.3f}).")
    if regime == "range" and uses_breakout_language:
        hard_reject_reasons.append("Range regime + breakout-style entry; high false-breakout risk.")

    signal_quality = 0.75
    if data_quality == "high":
        signal_quality += 0.05
    elif data_quality == "medium":
        signal_quality -= 0.08
        reasons.append("Data quality medium.")
    elif data_quality == "low":
        signal_quality -= 0.25
    else:
        signal_quality -= 0.12
        reasons.append("Data quality unknown.")

    signal_quality -= 0.06 * min(max(error_count, 0), 5)
    if error_count > 0:
        reasons.append(f"Tool errors observed: {error_count}.")
    if not structured_valid:
        signal_quality -= 0.10
        reasons.append("Structured validity false.")

    agreement_bonus = 0.0
    if rm_rating and rm_rating == rating:
        agreement_bonus += 0.02
    if trader_action and trader_action == rating:
        agreement_bonus += 0.01
    signal_quality = _clamp(signal_quality + agreement_bonus)

    market_quality = 0.55
    if regime == "trend":
        market_quality += 0.10
        market_quality += 0.10 * _clamp(regime_conf, 0.0, 1.0)
    elif regime == "range":
        market_quality += 0.02
    else:
        market_quality -= 0.12
        reasons.append("Regime unknown.")

    market_quality += _clamp(trend_strength * 6.0, 0.0, 0.15)

    if atr_pct >= 0.06:
        market_quality -= 0.18
        reasons.append("Volatility very high (ATR%).")
    elif atr_pct >= 0.04:
        market_quality -= 0.10
        reasons.append("Volatility high (ATR%).")
    elif atr_pct <= 0.015:
        market_quality -= 0.05
        reasons.append("Volatility very low (ATR%).")

    market_quality = _clamp(market_quality)

    execution_quality = 0.55
    if rr_target:
        execution_quality += _clamp((rr_target - 1.5) / 1.5, 0.0, 0.18)
    if stop_distance_pct >= 0.10:
        execution_quality -= 0.12
        reasons.append("Stop distance very wide.")
    elif stop_distance_pct >= 0.06:
        execution_quality -= 0.06
        reasons.append("Stop distance wide.")
    if "confirmation" in entry_condition or "retest" in entry_condition:
        execution_quality += 0.05
    if trade_levels.get("take_profit_1") is not None and trade_levels.get("take_profit_2") is not None:
        execution_quality += 0.03
    execution_quality = _clamp(execution_quality)

    if bias == "long" and rating in ("Sell", "Underweight"):
        market_quality -= 0.08
        reasons.append("Bias conflicts with bearish rating.")
    if bias == "short" and rating in ("Buy", "Overweight"):
        market_quality -= 0.08
        reasons.append("Bias conflicts with bullish rating.")
    market_quality = _clamp(market_quality)

    score = _clamp(0.50 * market_quality + 0.30 * execution_quality + 0.20 * signal_quality)
    passed = score >= float(threshold)

    filtered_out = bool(hard_reject_reasons) or not passed
    return {
        "filtered_out": filtered_out,
        "hard_reject": bool(hard_reject_reasons),
        "signal_quality": float(round(signal_quality, 3)),
        "market_quality": float(round(market_quality, 3)),
        "execution_quality": float(round(execution_quality, 3)),
        "score": float(round(score, 3)),
        "pass": bool(passed) and not bool(hard_reject_reasons),
        "threshold": float(threshold),
        "reasons": reasons,
        "hard_reject_reasons": hard_reject_reasons,
    }


def compute_trade_filter_score(
    *,
    trade_levels: Dict[str, Any] | None,
    rating: str,
    rm_rating: str | None,
    trader_action: str | None,
    data_quality: str,
    error_count: int,
    structured_valid: bool,
) -> Tuple[float, List[str]]:
    result = compute_trade_filter(
        trade_levels=trade_levels,
        rating=rating,
        rm_rating=rm_rating,
        trader_action=trader_action,
        data_quality=data_quality,
        error_count=error_count,
        structured_valid=structured_valid,
    )
    reasons = list(result.get("hard_reject_reasons", [])) + list(result.get("reasons", []))
    return float(result.get("score", 0.0)), reasons
