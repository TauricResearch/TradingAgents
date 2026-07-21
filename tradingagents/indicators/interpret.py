"""Rule-based interpretation of computed technical indicators.

Converts raw numeric indicator values into structured signals
(bullish / bearish / neutral) with confidence and human-readable
explanations.  No LLM involvement — pure deterministic rules.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def interpret_indicators(
    computed: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Interpret every indicator in *computed* and return structured signals.

    Each result dict contains: ``value``, ``signal``, ``confidence``, ``explanation``.
    Unknown indicators are silently skipped.
    """
    _INTERPRETERS: dict[str, Any] = {
        "rsi": _interpret_rsi,
        "macd": _interpret_macd,
        "bollinger": _interpret_bollinger,
        "sma_crossover": _interpret_sma_crossover,
    }

    results: dict[str, dict[str, Any]] = {}
    for name, data in computed.items():
        fn = _INTERPRETERS.get(name)
        if fn is not None:
            results[name] = fn(data)
    return results


# ---------------------------------------------------------------------------
# Per-indicator interpreters
# ---------------------------------------------------------------------------

def _interpret_rsi(data: dict[str, Any]) -> dict[str, Any]:
    val = data.get("value")
    if val is None:
        return _neutral(val, "Insufficient data for RSI")

    if val >= 80:
        return _signal(val, "bearish", 0.9, f"RSI {val:.1f} — strongly overbought")
    if val >= 70:
        return _signal(val, "bearish", 0.7, f"RSI {val:.1f} — overbought")
    if val <= 20:
        return _signal(val, "bullish", 0.9, f"RSI {val:.1f} — strongly oversold")
    if val <= 30:
        return _signal(val, "bullish", 0.7, f"RSI {val:.1f} — oversold")
    return _neutral(val, f"RSI {val:.1f} — neutral range")


def _interpret_macd(data: dict[str, Any]) -> dict[str, Any]:
    hist = data.get("histogram")
    macd_val = data.get("value")
    sig_val = data.get("signal")

    if hist is None or macd_val is None:
        return _neutral(macd_val, "Insufficient data for MACD")

    direction = "bullish" if hist > 0 else "bearish"
    # Confidence scales with histogram magnitude relative to signal line
    ref = abs(sig_val) if sig_val else 1.0
    strength = min(abs(hist) / max(ref, 0.01), 1.0)
    confidence = round(0.5 + 0.4 * strength, 2)

    crossing = ""
    if abs(hist) < 0.05 * max(ref, 0.01):
        crossing = " (near crossover)"
        confidence = 0.5

    return _signal(
        macd_val,
        direction,
        confidence,
        f"MACD histogram {hist:+.4f}{crossing} — {direction}",
    )


def _interpret_bollinger(data: dict[str, Any]) -> dict[str, Any]:
    price = data.get("value")
    upper = data.get("upper")
    lower = data.get("lower")

    if price is None or upper is None or lower is None:
        return _neutral(price, "Insufficient data for Bollinger Bands")

    band_width = upper - lower
    if band_width <= 0:
        return _neutral(price, "Bollinger band width is zero")

    position = (price - lower) / band_width  # 0 = at lower, 1 = at upper

    if position >= 1.0:
        return _signal(price, "bearish", 0.8, f"Price at/above upper Bollinger Band — overbought")
    if position >= 0.8:
        return _signal(price, "bearish", 0.6, f"Price near upper Bollinger Band ({position:.0%})")
    if position <= 0.0:
        return _signal(price, "bullish", 0.8, f"Price at/below lower Bollinger Band — oversold")
    if position <= 0.2:
        return _signal(price, "bullish", 0.6, f"Price near lower Bollinger Band ({position:.0%})")
    return _neutral(price, f"Price within Bollinger Bands ({position:.0%})")


def _interpret_sma_crossover(data: dict[str, Any]) -> dict[str, Any]:
    sma50 = data.get("sma50")
    sma200 = data.get("sma200")
    crossover = data.get("crossover")

    if sma50 is None or sma200 is None:
        return _neutral(sma50, "Insufficient data for SMA crossover")

    if crossover == "golden_cross":
        return _signal(sma50, "bullish", 0.85, "Golden cross — SMA50 crossed above SMA200")
    if crossover == "death_cross":
        return _signal(sma50, "bearish", 0.85, "Death cross — SMA50 crossed below SMA200")

    if sma50 > sma200:
        return _signal(sma50, "bullish", 0.6, f"SMA50 ({sma50:.2f}) above SMA200 ({sma200:.2f}) — bullish trend")
    return _signal(sma50, "bearish", 0.6, f"SMA50 ({sma50:.2f}) below SMA200 ({sma200:.2f}) — bearish trend")


def _interpret_support_resistance(data: dict[str, Any]) -> dict[str, Any]:
    price = data.get("last_close")
    resistance = data.get("resistance")
    support = data.get("support")

    if price is None or resistance is None or support is None:
        return _neutral(price, "Insufficient data for support/resistance")

    rng = resistance - support
    if rng <= 0:
        return _neutral(price, "Support equals resistance")

    position = (price - support) / rng

    if position >= 0.9:
        return _signal(price, "bearish", 0.65, f"Price near resistance ({resistance:.2f})")
    if position <= 0.1:
        return _signal(price, "bullish", 0.65, f"Price near support ({support:.2f})")
    return _neutral(price, f"Price between support ({support:.2f}) and resistance ({resistance:.2f})")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signal(
    value: Any, signal: str, confidence: float, explanation: str,
) -> dict[str, Any]:
    return {"value": value, "signal": signal, "confidence": confidence, "explanation": explanation}


def _neutral(value: Any, explanation: str) -> dict[str, Any]:
    return _signal(value, "neutral", 0.5, explanation)
