"""Deterministic OHLCV structure and pattern recognition.

The Portfolio State Manager uses this module as a hard-anchor producer.  The
rules here intentionally favor transparent, testable descriptions over perfect
chart-pattern artistry: every detected pattern carries the programmed feature
checks that fired, plus numeric evidence from the latest available bars.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Optional

import pandas as pd


def _load_pattern_features() -> dict[str, list[str]]:
    data = json.loads(
        resources.files(__package__).joinpath("pattern_features.json").read_text()
    )
    if not isinstance(data, dict):
        raise ValueError("pattern_features.json must contain an object keyed by pattern name.")
    for name, features in data.items():
        if not isinstance(name, str) or not isinstance(features, list):
            raise ValueError("pattern_features.json values must be lists of feature strings.")
        if not all(isinstance(feature, str) for feature in features):
            raise ValueError(f"pattern_features.json has non-string features for {name!r}.")
    return data


PATTERN_FEATURES: dict[str, list[str]] = _load_pattern_features()

ABBREVIATIONS = {
    "Break of Structure": "BOS",
    "Change of Character": "ChoCH",
    "Fair Value Gap": "FVG",
}

PATTERN_CATEGORIES = {
    "single_candlestick": {"Doji", "Hammer", "Shooting Star", "Marubozu"},
    "double_candlestick": {"Bullish Engulfing", "Bearish Engulfing", "Harami"},
    "three_candlestick": {
        "Morning Star",
        "Evening Star",
        "Three White Soldiers",
        "Three Black Crows",
    },
    "market_structure": {
        "Higher High Higher Low",
        "Lower High Lower Low",
        "Break of Structure",
        "Change of Character",
        "Consolidation",
        "Range Breakout",
    },
    "classical_chart": {
        "Head and Shoulders",
        "Inverse Head and Shoulders",
        "Double Top",
        "Double Bottom",
        "Triple Top",
        "Triple Bottom",
        "Ascending Triangle",
        "Descending Triangle",
        "Symmetrical Triangle",
        "Flag",
        "Pennant",
        "Wedge",
        "Cup and Handle",
    },
    "wyckoff": {"Accumulation", "Distribution", "Spring", "Upthrust"},
    "smc_ict": {
        "Liquidity Sweep",
        "Order Block",
        "Fair Value Gap",
        "Mitigation Block",
    },
}


@dataclass(frozen=True)
class SwingPoint:
    index: int
    date: str
    price: float


def analyze_ohlcv_structure(
    df: pd.DataFrame,
    ticker: str,
    as_of_date: Optional[str] = None,
) -> dict[str, Any]:
    """Return deterministic structure analysis for a ticker through as_of_date."""
    clean = _prepare_ohlcv(df)
    if as_of_date:
        cutoff = pd.to_datetime(as_of_date).normalize()
        clean = clean[clean["Date"] <= cutoff]
    clean = clean.tail(260).reset_index(drop=True)

    if len(clean) < 5:
        return _empty_analysis(ticker, as_of_date, "insufficient OHLCV history")

    enriched = _add_bar_features(clean)
    highs, lows = _find_swings(enriched)
    detected: list[dict[str, Any]] = []

    detected.extend(_detect_single_candle_patterns(enriched))
    detected.extend(_detect_double_candle_patterns(enriched))
    detected.extend(_detect_three_candle_patterns(enriched))
    detected.extend(_detect_market_structure_patterns(enriched, highs, lows))
    detected.extend(_detect_classical_chart_patterns(enriched, highs, lows))
    detected.extend(_detect_wyckoff_patterns(enriched, highs, lows))
    detected.extend(_detect_smc_ict_patterns(enriched))

    detected = sorted(
        _dedupe_patterns(detected),
        key=lambda item: (item["confidence"], item["lookback_days"] * -1),
        reverse=True,
    )

    short_term = _short_term_structure(enriched, highs, lows, detected)
    long_term = _long_term_structure(enriched, highs, lows, detected)
    conflicts = _structure_conflicts(short_term, long_term, detected)
    as_of = pd.to_datetime(enriched.iloc[-1]["Date"]).strftime("%Y-%m-%d")

    return {
        "schema_version": "structure_v1",
        "ticker": ticker,
        "as_of_date": as_of,
        "short_term_structure": short_term,
        "long_term_structure": long_term,
        "detected_patterns": detected[:12],
        "conflicts": conflicts,
        "feature_rule_summary": {
            "candlestick": (
                "Body, wick, engulfing, inside-candle, and three-candle reversal "
                "rules are computed from the latest daily OHLC bars."
            ),
            "market_structure": (
                "Swing highs/lows use confirmed local pivots; HH/HL, LL/LH, BOS, "
                "ChoCH, consolidation, and range breakout are derived from those pivots."
            ),
            "classical_wyckoff_smc": (
                "Chart, Wyckoff, and SMC/ICT labels are heuristic compressions of "
                "pivot geometry, recent range behavior, false breaks, gaps, and displacement."
            ),
        },
    }


def format_structure_analysis_for_prompt(analysis: Optional[dict[str, Any]]) -> str:
    """Compact deterministic structure analysis for PortfolioState prompts."""
    if not analysis:
        return "**Deterministic structure analysis:** unavailable\n"

    short = analysis.get("short_term_structure") or {}
    long = analysis.get("long_term_structure") or {}
    patterns = analysis.get("detected_patterns") or []
    conflicts = analysis.get("conflicts") or []

    def _fmt(value: Any) -> str:
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.4g}"
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) if value else "none"
        return str(value)

    lines = [
        "**Deterministic structure analysis (Python-only hard anchor; do not reinterpret from prose):**",
        f"- schema_version: {analysis.get('schema_version', 'structure_v1')}",
        f"- as_of_date: {analysis.get('as_of_date', 'n/a')}",
        (
            "- short_term: "
            f"trend={_fmt(short.get('trend'))}, "
            f"quality={_fmt(short.get('structure_quality'))}, "
            f"pattern={_fmt(short.get('pattern'))}, "
            f"breakout_status={_fmt(short.get('breakout_status'))}, "
            f"support={_fmt(short.get('support'))}, "
            f"resistance={_fmt(short.get('resistance'))}, "
            f"volume={_fmt(short.get('volume_confirmation'))}, "
            f"confidence={_fmt(short.get('confidence'))}"
        ),
        (
            "- long_term: "
            f"trend={_fmt(long.get('trend'))}, "
            f"market_phase={_fmt(long.get('market_phase'))}, "
            f"key_level={_fmt(long.get('key_level'))}, "
            f"risk_state={_fmt(long.get('risk_state'))}, "
            f"confidence={_fmt(long.get('confidence'))}"
        ),
    ]

    if patterns:
        lines.append("- detected_patterns:")
        for pattern in patterns[:8]:
            abbreviation = pattern.get("abbreviation")
            name = pattern["name"] + (f" ({abbreviation})" if abbreviation else "")
            lines.append(
                "  - "
                f"{pattern['category']} | {name} | "
                f"direction={pattern.get('direction', 'neutral')} | "
                f"confidence={_fmt(pattern.get('confidence'))} | "
                f"features={'; '.join(pattern.get('matched_features') or [])} | "
                f"evidence={pattern.get('evidence', '')}"
            )
    else:
        lines.append("- detected_patterns: none")

    lines.append(f"- conflicts: {_fmt(conflicts)}")
    return "\n".join(lines) + "\n"


def _prepare_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce")
    clean = clean.dropna(subset=["Date"])
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        if column not in clean:
            clean[column] = pd.NA
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna(subset=["Open", "High", "Low", "Close"])
    clean = clean.sort_values("Date").reset_index(drop=True)
    return clean


def _add_bar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["range"] = (out["High"] - out["Low"]).clip(lower=0.0)
    out["body"] = (out["Close"] - out["Open"]).abs()
    out["upper_wick"] = out["High"] - out[["Open", "Close"]].max(axis=1)
    out["lower_wick"] = out[["Open", "Close"]].min(axis=1) - out["Low"]
    out["body_ratio"] = _safe_div(out["body"], out["range"])
    out["upper_ratio"] = _safe_div(out["upper_wick"], out["range"])
    out["lower_ratio"] = _safe_div(out["lower_wick"], out["range"])
    out["close_position"] = _safe_div(out["Close"] - out["Low"], out["range"])
    out["direction"] = "flat"
    out.loc[out["Close"] > out["Open"], "direction"] = "bullish"
    out.loc[out["Close"] < out["Open"], "direction"] = "bearish"
    out["ema5"] = out["Close"].ewm(span=5, adjust=False).mean()
    out["ema10"] = out["Close"].ewm(span=10, adjust=False).mean()
    out["ema20"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["sma20"] = out["Close"].rolling(20).mean()
    out["sma50"] = out["Close"].rolling(50).mean()
    out["sma200"] = out["Close"].rolling(200).mean()
    out["atr14"] = _atr(out, 14)
    out["volume_sma20"] = out["Volume"].rolling(20).mean()
    out["volume_ratio20"] = _safe_div(out["Volume"], out["volume_sma20"])
    return out


def _safe_div(numerator, denominator):
    result = numerator / denominator.replace(0, pd.NA)
    return result.fillna(0.0)


def _atr(df: pd.DataFrame, window: int) -> pd.Series:
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window).mean()


def _empty_analysis(ticker: str, as_of_date: Optional[str], reason: str) -> dict[str, Any]:
    return {
        "schema_version": "structure_v1",
        "ticker": ticker,
        "as_of_date": as_of_date,
        "short_term_structure": {
            "trend": "unclear",
            "structure_quality": "unclear",
            "pattern": "none",
            "breakout_status": "none",
            "support": None,
            "resistance": None,
            "volume_confirmation": "unavailable",
            "confidence": 0.0,
        },
        "long_term_structure": {
            "trend": "unclear",
            "market_phase": "unclear",
            "key_level": None,
            "risk_state": "unavailable",
            "confidence": 0.0,
        },
        "detected_patterns": [],
        "conflicts": [reason],
        "feature_rule_summary": {},
    }


def _find_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> tuple[list[SwingPoint], list[SwingPoint]]:
    highs: list[SwingPoint] = []
    lows: list[SwingPoint] = []
    for idx in range(left, len(df) - right):
        high_window = df["High"].iloc[idx - left : idx + right + 1]
        low_window = df["Low"].iloc[idx - left : idx + right + 1]
        row = df.iloc[idx]
        date = pd.to_datetime(row["Date"]).strftime("%Y-%m-%d")
        if row["High"] == high_window.max() and high_window.tolist().count(row["High"]) == 1:
            highs.append(SwingPoint(idx, date, round(float(row["High"]), 4)))
        if row["Low"] == low_window.min() and low_window.tolist().count(row["Low"]) == 1:
            lows.append(SwingPoint(idx, date, round(float(row["Low"]), 4)))
    return highs, lows


def _pattern(
    name: str,
    category: str,
    direction: str,
    confidence: float,
    matched_features: list[str],
    evidence: str,
    lookback_days: int,
) -> dict[str, Any]:
    item = {
        "name": name,
        "category": category,
        "direction": direction,
        "confidence": round(min(max(confidence, 0.0), 1.0), 2),
        "structure_features": PATTERN_FEATURES[name],
        "matched_features": matched_features,
        "evidence": evidence,
        "lookback_days": lookback_days,
    }
    if name in ABBREVIATIONS:
        item["abbreviation"] = ABBREVIATIONS[name]
    return item


def _recent_downtrend(df: pd.DataFrame, lookback: int = 6) -> bool:
    if len(df) < lookback + 1:
        return False
    window = df.tail(lookback + 1)
    return float(window["Close"].iloc[-2]) < float(window["Close"].iloc[0]) and (
        float(df.iloc[-2]["Close"]) < float(df.iloc[-2]["ema10"])
    )


def _recent_uptrend(df: pd.DataFrame, lookback: int = 6) -> bool:
    if len(df) < lookback + 1:
        return False
    window = df.tail(lookback + 1)
    return float(window["Close"].iloc[-2]) > float(window["Close"].iloc[0]) and (
        float(df.iloc[-2]["Close"]) > float(df.iloc[-2]["ema10"])
    )


def _detect_single_candle_patterns(df: pd.DataFrame) -> list[dict[str, Any]]:
    row = df.iloc[-1]
    prev = df.iloc[:-1]
    patterns = []
    body_ratio = float(row["body_ratio"])
    upper_ratio = float(row["upper_ratio"])
    lower_ratio = float(row["lower_ratio"])
    close_pos = float(row["close_position"])
    date = pd.to_datetime(row["Date"]).strftime("%Y-%m-%d")

    if body_ratio <= 0.12 and upper_ratio >= 0.18 and lower_ratio >= 0.18:
        patterns.append(_pattern(
            "Doji",
            "single_candlestick",
            "neutral",
            0.70,
            ["open approximately equals close", "upper and lower wick present"],
            f"{date}: body/range={body_ratio:.2f}, upper={upper_ratio:.2f}, lower={lower_ratio:.2f}",
            1,
        ))

    prior_support = float(prev["Low"].tail(10).min()) if len(prev) >= 10 else float(prev["Low"].min())
    swept_support = float(row["Low"]) < prior_support and float(row["Close"]) > prior_support
    if (
        lower_ratio >= 0.50
        and body_ratio <= 0.35
        and close_pos >= 0.60
        and (_recent_downtrend(df) or swept_support)
    ):
        features = ["long lower wick", "small real body near top"]
        if _recent_downtrend(df):
            features.append("appears after downtrend")
        if swept_support:
            features.append("liquidity sweep below support")
        if float(row["Close"]) >= float(row["Open"]) or close_pos >= 0.70:
            features.append("buying absorption")
        patterns.append(_pattern(
            "Hammer",
            "single_candlestick",
            "bullish",
            0.65 + (0.10 if swept_support else 0.0),
            features,
            f"{date}: lower_wick/range={lower_ratio:.2f}, close_position={close_pos:.2f}, prior_support={prior_support:.4g}",
            1,
        ))

    prior_resistance = float(prev["High"].tail(10).max()) if len(prev) >= 10 else float(prev["High"].max())
    failed_breakout = float(row["High"]) > prior_resistance and float(row["Close"]) < prior_resistance
    if (
        upper_ratio >= 0.50
        and body_ratio <= 0.35
        and close_pos <= 0.40
        and (_recent_uptrend(df) or failed_breakout)
    ):
        features = ["long upper wick", "small real body near bottom"]
        if _recent_uptrend(df):
            features.append("appears after uptrend")
        if failed_breakout:
            features.append("failed breakout")
        if float(row["Close"]) <= float(row["Open"]) or close_pos <= 0.30:
            features.append("seller rejection")
        patterns.append(_pattern(
            "Shooting Star",
            "single_candlestick",
            "bearish",
            0.65 + (0.10 if failed_breakout else 0.0),
            features,
            f"{date}: upper_wick/range={upper_ratio:.2f}, close_position={close_pos:.2f}, prior_resistance={prior_resistance:.4g}",
            1,
        ))

    if body_ratio >= 0.80 and upper_ratio <= 0.10 and lower_ratio <= 0.10:
        direction = "bullish" if row["Close"] > row["Open"] else "bearish"
        patterns.append(_pattern(
            "Marubozu",
            "single_candlestick",
            direction,
            0.72,
            ["little or no wick", "strong directional momentum", "dominant orderflow"],
            f"{date}: body/range={body_ratio:.2f}, upper={upper_ratio:.2f}, lower={lower_ratio:.2f}",
            1,
        ))
    return patterns


def _detect_double_candle_patterns(df: pd.DataFrame) -> list[dict[str, Any]]:
    if len(df) < 2:
        return []
    prev, curr = df.iloc[-2], df.iloc[-1]
    patterns = []
    prev_low_body = min(float(prev["Open"]), float(prev["Close"]))
    prev_high_body = max(float(prev["Open"]), float(prev["Close"]))
    curr_low_body = min(float(curr["Open"]), float(curr["Close"]))
    curr_high_body = max(float(curr["Open"]), float(curr["Close"]))
    date = pd.to_datetime(curr["Date"]).strftime("%Y-%m-%d")

    if (
        prev["direction"] == "bearish"
        and curr["direction"] == "bullish"
        and curr_low_body <= prev_low_body
        and curr_high_body >= prev_high_body
    ):
        patterns.append(_pattern(
            "Bullish Engulfing",
            "double_candlestick",
            "bullish",
            0.74,
            [
                "second bullish candle fully engulfs previous bearish candle",
                "strong buyer takeover",
                "momentum reversal",
            ],
            f"{date}: current real body [{curr_low_body:.4g}, {curr_high_body:.4g}] engulfs previous [{prev_low_body:.4g}, {prev_high_body:.4g}]",
            2,
        ))

    if (
        prev["direction"] == "bullish"
        and curr["direction"] == "bearish"
        and curr_low_body <= prev_low_body
        and curr_high_body >= prev_high_body
    ):
        patterns.append(_pattern(
            "Bearish Engulfing",
            "double_candlestick",
            "bearish",
            0.74,
            [
                "second bearish candle fully engulfs previous bullish candle",
                "strong seller takeover",
                "momentum reversal",
            ],
            f"{date}: current real body [{curr_low_body:.4g}, {curr_high_body:.4g}] engulfs previous [{prev_low_body:.4g}, {prev_high_body:.4g}]",
            2,
        ))

    if (
        float(prev["body_ratio"]) >= 0.45
        and float(curr["body_ratio"]) <= 0.35
        and curr_low_body >= prev_low_body
        and curr_high_body <= prev_high_body
    ):
        patterns.append(_pattern(
            "Harami",
            "double_candlestick",
            "neutral",
            0.62,
            ["small candle inside previous large candle", "volatility contraction", "market pause"],
            f"{date}: small body [{curr_low_body:.4g}, {curr_high_body:.4g}] inside previous body [{prev_low_body:.4g}, {prev_high_body:.4g}]",
            2,
        ))
    return patterns


def _detect_three_candle_patterns(df: pd.DataFrame) -> list[dict[str, Any]]:
    if len(df) < 3:
        return []
    a, b, c = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    patterns = []
    date = pd.to_datetime(c["Date"]).strftime("%Y-%m-%d")
    a_mid = (float(a["Open"]) + float(a["Close"])) / 2.0

    if (
        a["direction"] == "bearish"
        and float(a["body_ratio"]) >= 0.45
        and float(b["body_ratio"]) <= 0.30
        and c["direction"] == "bullish"
        and float(c["Close"]) > a_mid
    ):
        patterns.append(_pattern(
            "Morning Star",
            "three_candlestick",
            "bullish",
            0.72,
            ["downtrend candle", "indecision candle", "strong bullish recovery", "trend exhaustion"],
            f"{date}: third close {float(c['Close']):.4g} recovered above first-candle midpoint {a_mid:.4g}",
            3,
        ))

    if (
        a["direction"] == "bullish"
        and float(a["body_ratio"]) >= 0.45
        and float(b["body_ratio"]) <= 0.30
        and c["direction"] == "bearish"
        and float(c["Close"]) < a_mid
    ):
        patterns.append(_pattern(
            "Evening Star",
            "three_candlestick",
            "bearish",
            0.72,
            ["uptrend candle", "indecision candle", "strong bearish reversal", "trend exhaustion"],
            f"{date}: third close {float(c['Close']):.4g} fell below first-candle midpoint {a_mid:.4g}",
            3,
        ))

    last3 = df.tail(3)
    if all(last3["direction"] == "bullish") and all(last3["Close"].diff().dropna() > 0):
        patterns.append(_pattern(
            "Three White Soldiers",
            "three_candlestick",
            "bullish",
            0.68,
            ["three consecutive bullish candles", "strong bullish continuation"],
            f"{date}: three bullish closes from {float(last3['Close'].iloc[0]):.4g} to {float(last3['Close'].iloc[-1]):.4g}",
            3,
        ))

    if all(last3["direction"] == "bearish") and all(last3["Close"].diff().dropna() < 0):
        patterns.append(_pattern(
            "Three Black Crows",
            "three_candlestick",
            "bearish",
            0.68,
            ["three consecutive bearish candles", "strong bearish continuation", "persistent selling pressure"],
            f"{date}: three bearish closes from {float(last3['Close'].iloc[0]):.4g} to {float(last3['Close'].iloc[-1]):.4g}",
            3,
        ))
    return patterns


def _detect_market_structure_patterns(
    df: pd.DataFrame,
    highs: list[SwingPoint],
    lows: list[SwingPoint],
) -> list[dict[str, Any]]:
    patterns = []
    close = float(df.iloc[-1]["Close"])
    atr = _latest_atr(df)
    recent = df.tail(min(20, len(df)))
    recent_range = float(recent["High"].max() - recent["Low"].min())
    current_date = pd.to_datetime(df.iloc[-1]["Date"]).strftime("%Y-%m-%d")

    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price:
            patterns.append(_pattern(
                "Higher High Higher Low",
                "market_structure",
                "bullish",
                0.76,
                ["successive higher highs", "successive higher lows", "uptrend structure"],
                f"{current_date}: highs {highs[-2].price:g}->{highs[-1].price:g}, lows {lows[-2].price:g}->{lows[-1].price:g}",
                highs[-1].index - lows[-2].index if highs[-1].index > lows[-2].index else 20,
            ))
        if highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price:
            patterns.append(_pattern(
                "Lower High Lower Low",
                "market_structure",
                "bearish",
                0.76,
                ["successive lower highs", "successive lower lows", "downtrend structure"],
                f"{current_date}: highs {highs[-2].price:g}->{highs[-1].price:g}, lows {lows[-2].price:g}->{lows[-1].price:g}",
                lows[-1].index - highs[-2].index if lows[-1].index > highs[-2].index else 20,
            ))

    last_high = highs[-1].price if highs else None
    last_low = lows[-1].price if lows else None
    prior_trend = _swing_trend(highs[:-1], lows[:-1])
    if last_high is not None and close > last_high:
        patterns.append(_pattern(
            "Break of Structure",
            "market_structure",
            "bullish",
            0.75,
            ["key swing point broken", "trend transition", "structure invalidation"],
            f"{current_date}: close {close:.4g} broke prior swing high {last_high:.4g}",
            10,
        ))
        if prior_trend == "downtrend":
            patterns.append(_pattern(
                "Change of Character",
                "market_structure",
                "bullish",
                0.70,
                ["first major structural reversal", "possible regime shift"],
                f"{current_date}: bullish break followed prior downtrend swing structure",
                20,
            ))
    if last_low is not None and close < last_low:
        patterns.append(_pattern(
            "Break of Structure",
            "market_structure",
            "bearish",
            0.75,
            ["key swing point broken", "trend transition", "structure invalidation"],
            f"{current_date}: close {close:.4g} broke prior swing low {last_low:.4g}",
            10,
        ))
        if prior_trend == "uptrend":
            patterns.append(_pattern(
                "Change of Character",
                "market_structure",
                "bearish",
                0.70,
                ["first major structural reversal", "possible regime shift"],
                f"{current_date}: bearish break followed prior uptrend swing structure",
                20,
            ))

    if len(recent) >= 12 and atr > 0 and recent_range <= 3.0 * atr:
        patterns.append(_pattern(
            "Consolidation",
            "market_structure",
            "neutral",
            0.65,
            ["sideways movement", "volatility compression", "temporary equilibrium"],
            f"{current_date}: 20-bar range {recent_range:.4g} <= 3x ATR14 {atr:.4g}",
            len(recent),
        ))

    if len(df) >= 21:
        prior = df.iloc[-21:-1]
        prior_high = float(prior["High"].max())
        prior_low = float(prior["Low"].min())
        vol_ratio = float(df.iloc[-1].get("volume_ratio20", 0.0))
        if close > prior_high or close < prior_low:
            direction = "bullish" if close > prior_high else "bearish"
            level = prior_high if close > prior_high else prior_low
            patterns.append(_pattern(
                "Range Breakout",
                "market_structure",
                direction,
                0.66 + (0.08 if vol_ratio >= 1.2 else 0.0),
                ["break outside consolidation range", "volatility expansion", "price discovery"],
                f"{current_date}: close {close:.4g} broke 20-bar level {level:.4g}, volume_ratio20={vol_ratio:.2f}",
                20,
            ))
    return patterns


def _detect_classical_chart_patterns(
    df: pd.DataFrame,
    highs: list[SwingPoint],
    lows: list[SwingPoint],
) -> list[dict[str, Any]]:
    patterns = []
    date = pd.to_datetime(df.iloc[-1]["Date"]).strftime("%Y-%m-%d")
    tolerance = 0.018

    if len(highs) >= 2 and _near(highs[-1].price, highs[-2].price, tolerance):
        patterns.append(_pattern(
            "Double Top",
            "classical_chart",
            "bearish",
            0.62,
            ["two failed highs", "resistance rejection", "bearish reversal potential"],
            f"{date}: swing highs {highs[-2].price:g} and {highs[-1].price:g} within {tolerance:.1%}",
            40,
        ))
    if len(lows) >= 2 and _near(lows[-1].price, lows[-2].price, tolerance):
        patterns.append(_pattern(
            "Double Bottom",
            "classical_chart",
            "bullish",
            0.62,
            ["two failed lows", "support holding", "bullish reversal potential"],
            f"{date}: swing lows {lows[-2].price:g} and {lows[-1].price:g} within {tolerance:.1%}",
            40,
        ))
    if len(highs) >= 3 and _clustered([point.price for point in highs[-3:]], tolerance):
        patterns.append(_pattern(
            "Triple Top",
            "classical_chart",
            "bearish",
            0.64,
            ["three failed highs", "strong resistance zone"],
            f"{date}: last three swing highs clustered near {_mean([point.price for point in highs[-3:]]):.4g}",
            60,
        ))
    if len(lows) >= 3 and _clustered([point.price for point in lows[-3:]], tolerance):
        patterns.append(_pattern(
            "Triple Bottom",
            "classical_chart",
            "bullish",
            0.64,
            ["three failed lows", "strong support zone"],
            f"{date}: last three swing lows clustered near {_mean([point.price for point in lows[-3:]]):.4g}",
            60,
        ))

    if len(highs) >= 3:
        h = highs[-3:]
        if h[1].price > h[0].price and h[1].price > h[2].price and _near(h[0].price, h[2].price, 0.04):
            patterns.append(_pattern(
                "Head and Shoulders",
                "classical_chart",
                "bearish",
                0.58,
                ["three peaks", "middle peak highest", "trend exhaustion", "bearish reversal"],
                f"{date}: peak sequence {h[0].price:g}, {h[1].price:g}, {h[2].price:g}",
                80,
            ))
    if len(lows) >= 3:
        l = lows[-3:]
        if l[1].price < l[0].price and l[1].price < l[2].price and _near(l[0].price, l[2].price, 0.04):
            patterns.append(_pattern(
                "Inverse Head and Shoulders",
                "classical_chart",
                "bullish",
                0.58,
                ["three troughs", "middle trough lowest", "bullish reversal"],
                f"{date}: trough sequence {l[0].price:g}, {l[1].price:g}, {l[2].price:g}",
                80,
            ))

    if len(highs) >= 2 and len(lows) >= 2:
        last_highs = highs[-3:] if len(highs) >= 3 else highs[-2:]
        last_lows = lows[-3:] if len(lows) >= 3 else lows[-2:]
        flat_resistance = _clustered([point.price for point in last_highs], 0.02)
        flat_support = _clustered([point.price for point in last_lows], 0.02)
        rising_lows = all(b.price > a.price for a, b in zip(last_lows, last_lows[1:]))
        falling_highs = all(b.price < a.price for a, b in zip(last_highs, last_highs[1:]))

        if flat_resistance and rising_lows:
            patterns.append(_pattern(
                "Ascending Triangle",
                "classical_chart",
                "bullish",
                0.62,
                ["flat resistance", "rising lows", "buying pressure increasing"],
                f"{date}: resistance clustered near {_mean([p.price for p in last_highs]):.4g}, lows rising",
                60,
            ))
        if flat_support and falling_highs:
            patterns.append(_pattern(
                "Descending Triangle",
                "classical_chart",
                "bearish",
                0.62,
                ["flat support", "falling highs", "selling pressure increasing"],
                f"{date}: support clustered near {_mean([p.price for p in last_lows]):.4g}, highs falling",
                60,
            ))
        if falling_highs and rising_lows:
            patterns.append(_pattern(
                "Symmetrical Triangle",
                "classical_chart",
                "neutral",
                0.60,
                ["converging highs and lows", "volatility compression", "breakout setup"],
                f"{date}: swing highs falling while swing lows rise",
                60,
            ))
        same_direction = (
            all(b.price > a.price for a, b in zip(last_highs, last_highs[1:]))
            and rising_lows
        ) or (
            falling_highs
            and all(b.price < a.price for a, b in zip(last_lows, last_lows[1:]))
        )
        range_now = max(p.price for p in last_highs) - min(p.price for p in last_lows)
        range_prev = float(df["High"].tail(60).max() - df["Low"].tail(60).min())
        if same_direction and range_prev > 0 and range_now < 0.65 * range_prev:
            direction = "bearish" if falling_highs else "bullish"
            patterns.append(_pattern(
                "Wedge",
                "classical_chart",
                direction,
                0.56,
                ["converging trend lines", "slowing trend momentum", "possible reversal"],
                f"{date}: same-direction swing lines with compressed recent range",
                60,
            ))

    patterns.extend(_detect_flag_pennant_cup(df))
    return patterns


def _detect_flag_pennant_cup(df: pd.DataFrame) -> list[dict[str, Any]]:
    patterns = []
    if len(df) < 25:
        return patterns
    date = pd.to_datetime(df.iloc[-1]["Date"]).strftime("%Y-%m-%d")
    impulse = df.iloc[-15:-8]
    consolidation = df.tail(8)
    impulse_return = float(impulse["Close"].iloc[-1] / impulse["Close"].iloc[0] - 1.0)
    consolidation_range = float(consolidation["High"].max() - consolidation["Low"].min())
    impulse_range = float(impulse["High"].max() - impulse["Low"].min())
    if abs(impulse_return) >= 0.04 and impulse_range > 0 and consolidation_range <= 0.55 * impulse_range:
        direction = "bullish" if impulse_return > 0 else "bearish"
        patterns.append(_pattern(
            "Flag",
            "classical_chart",
            direction,
            0.58,
            ["sharp move followed by small channel", "trend continuation"],
            f"{date}: impulse_return={impulse_return:.1%}, consolidation_range/impulse_range={consolidation_range / impulse_range:.2f}",
            15,
        ))
        if consolidation["High"].is_monotonic_decreasing and consolidation["Low"].is_monotonic_increasing:
            patterns.append(_pattern(
                "Pennant",
                "classical_chart",
                direction,
                0.57,
                ["sharp move followed by small triangle", "volatility compression", "trend continuation"],
                f"{date}: post-impulse highs/lows converged over 8 bars",
                15,
            ))

    if len(df) >= 80:
        window = df.tail(80).reset_index(drop=True)
        trough_idx = int(window["Low"].idxmin())
        left_high = float(window["High"].iloc[: max(trough_idx, 1)].max())
        right_high = float(window["High"].iloc[trough_idx + 1 :].max())
        trough = float(window["Low"].iloc[trough_idx])
        recent_pullback = float(window["Close"].tail(8).max() - window["Close"].iloc[-1])
        depth = min(left_high, right_high) - trough
        if 15 < trough_idx < 60 and depth > 0 and _near(left_high, right_high, 0.08) and recent_pullback <= 0.35 * depth:
            patterns.append(_pattern(
                "Cup and Handle",
                "classical_chart",
                "bullish",
                0.54,
                ["rounded bottom", "small pullback handle", "long-term accumulation"],
                f"{date}: 80-bar trough centered with rim highs {left_high:.4g}/{right_high:.4g}",
                80,
            ))
    return patterns


def _detect_wyckoff_patterns(
    df: pd.DataFrame,
    highs: list[SwingPoint],
    lows: list[SwingPoint],
) -> list[dict[str, Any]]:
    patterns = []
    if len(df) < 30:
        return patterns
    date = pd.to_datetime(df.iloc[-1]["Date"]).strftime("%Y-%m-%d")
    recent = df.tail(20)
    prior = df.iloc[-50:-20] if len(df) >= 50 else df.iloc[:-20]
    recent_range_pct = float((recent["High"].max() - recent["Low"].min()) / recent["Close"].iloc[-1])
    prior_return = float(prior["Close"].iloc[-1] / prior["Close"].iloc[0] - 1.0) if len(prior) >= 5 else 0.0

    if recent_range_pct <= 0.08 and prior_return <= -0.06:
        patterns.append(_pattern(
            "Accumulation",
            "wyckoff",
            "bullish",
            0.56,
            ["sideways range after decline", "institutional buying", "supply absorption"],
            f"{date}: prior_return={prior_return:.1%}, recent_range_pct={recent_range_pct:.1%}",
            50,
        ))
    if recent_range_pct <= 0.08 and prior_return >= 0.06:
        patterns.append(_pattern(
            "Distribution",
            "wyckoff",
            "bearish",
            0.56,
            ["sideways range after rally", "institutional selling", "demand exhaustion"],
            f"{date}: prior_return={prior_return:.1%}, recent_range_pct={recent_range_pct:.1%}",
            50,
        ))

    if len(df) >= 21:
        latest = df.iloc[-1]
        support = float(df.iloc[-21:-1]["Low"].min())
        resistance = float(df.iloc[-21:-1]["High"].max())
        if float(latest["Low"]) < support and float(latest["Close"]) > support:
            patterns.append(_pattern(
                "Spring",
                "wyckoff",
                "bullish",
                0.68,
                ["false breakdown below support", "liquidity grab", "rapid recovery"],
                f"{date}: low {float(latest['Low']):.4g} swept support {support:.4g}, close recovered",
                20,
            ))
        if float(latest["High"]) > resistance and float(latest["Close"]) < resistance:
            patterns.append(_pattern(
                "Upthrust",
                "wyckoff",
                "bearish",
                0.68,
                ["false breakout above resistance", "bull trap", "reversal rejection"],
                f"{date}: high {float(latest['High']):.4g} swept resistance {resistance:.4g}, close rejected",
                20,
            ))
    return patterns


def _detect_smc_ict_patterns(df: pd.DataFrame) -> list[dict[str, Any]]:
    patterns = []
    date = pd.to_datetime(df.iloc[-1]["Date"]).strftime("%Y-%m-%d")
    latest = df.iloc[-1]
    if len(df) >= 21:
        support = float(df.iloc[-21:-1]["Low"].min())
        resistance = float(df.iloc[-21:-1]["High"].max())
        if float(latest["Low"]) < support and float(latest["Close"]) > support:
            patterns.append(_pattern(
                "Liquidity Sweep",
                "smc_ict",
                "bullish",
                0.67,
                ["stop-loss hunting", "temporary breakout", "rapid reversal"],
                f"{date}: downside sweep below {support:.4g} closed back inside range",
                20,
            ))
        if float(latest["High"]) > resistance and float(latest["Close"]) < resistance:
            patterns.append(_pattern(
                "Liquidity Sweep",
                "smc_ict",
                "bearish",
                0.67,
                ["stop-loss hunting", "temporary breakout", "rapid reversal"],
                f"{date}: upside sweep above {resistance:.4g} closed back inside range",
                20,
            ))

    recent_fvg = _latest_fvg(df)
    if recent_fvg is not None:
        direction, low, high, idx = recent_fvg
        patterns.append(_pattern(
            "Fair Value Gap",
            "smc_ict",
            direction,
            0.58,
            ["price imbalance", "low traded region", "fast displacement"],
            f"{date}: latest {direction} imbalance from {low:.4g} to {high:.4g} at bar_index={idx}",
            len(df) - idx,
        ))
        close = float(latest["Close"])
        if low <= close <= high:
            patterns.append(_pattern(
                "Mitigation Block",
                "smc_ict",
                "neutral",
                0.55,
                ["return to previous imbalance zone", "liquidity rebalance"],
                f"{date}: close {close:.4g} returned into FVG zone [{low:.4g}, {high:.4g}]",
                len(df) - idx,
            ))

    displacement_idx = _latest_displacement_index(df)
    if displacement_idx is not None and displacement_idx > 0:
        prev = df.iloc[displacement_idx - 1]
        disp = df.iloc[displacement_idx]
        direction = "bullish" if disp["Close"] > disp["Open"] else "bearish"
        opposite_prev = (
            direction == "bullish" and prev["Close"] < prev["Open"]
        ) or (
            direction == "bearish" and prev["Close"] > prev["Open"]
        )
        if opposite_prev:
            low = min(float(prev["Open"]), float(prev["Close"]))
            high = max(float(prev["Open"]), float(prev["Close"]))
            patterns.append(_pattern(
                "Order Block",
                "smc_ict",
                direction,
                0.54,
                ["institutional transaction zone", "strong reaction area"],
                f"{date}: prior opposite candle body zone [{low:.4g}, {high:.4g}] before displacement",
                len(df) - displacement_idx,
            ))
    return patterns


def _latest_fvg(df: pd.DataFrame) -> Optional[tuple[str, float, float, int]]:
    if len(df) < 3:
        return None
    start = max(2, len(df) - 20)
    for idx in range(len(df) - 1, start - 1, -1):
        left = df.iloc[idx - 2]
        right = df.iloc[idx]
        if float(right["Low"]) > float(left["High"]):
            return "bullish", float(left["High"]), float(right["Low"]), idx
        if float(right["High"]) < float(left["Low"]):
            return "bearish", float(right["High"]), float(left["Low"]), idx
    return None


def _latest_displacement_index(df: pd.DataFrame) -> Optional[int]:
    atr = df["atr14"].fillna(0.0)
    start = max(1, len(df) - 10)
    for idx in range(len(df) - 1, start - 1, -1):
        row = df.iloc[idx]
        if float(atr.iloc[idx]) > 0 and float(row["body"]) >= 1.2 * float(atr.iloc[idx]):
            return idx
    return None


def _short_term_structure(
    df: pd.DataFrame,
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    patterns: list[dict[str, Any]],
) -> dict[str, Any]:
    latest = df.iloc[-1]
    close = float(latest["Close"])
    ema5 = float(latest["ema5"])
    ema10 = float(latest["ema10"])
    ema20 = float(latest["ema20"])
    recent_high = float(df["High"].tail(20).max())
    recent_low = float(df["Low"].tail(20).min())
    support = _nearest_level_below([point.price for point in lows], close) or recent_low
    resistance = _nearest_level_above([point.price for point in highs], close) or recent_high
    swing_trend = _swing_trend(highs, lows)

    if close > ema5 > ema10 > ema20 or swing_trend == "uptrend":
        trend = "ascending"
    elif close < ema5 < ema10 < ema20 or swing_trend == "downtrend":
        trend = "descending"
    elif _is_consolidating(df.tail(20)):
        trend = "sideways"
    else:
        trend = "transition"

    top = _dominant_pattern(patterns, {"single_candlestick", "double_candlestick", "three_candlestick", "market_structure"})
    bearish_reversal = any(p["direction"] == "bearish" and p["confidence"] >= 0.66 for p in patterns[:5])
    bullish_reversal = any(p["direction"] == "bullish" and p["confidence"] >= 0.66 for p in patterns[:5])
    consolidation = any(p["name"] == "Consolidation" for p in patterns)

    if consolidation:
        quality = "range_bound"
    elif trend in {"ascending", "descending"} and not (bearish_reversal and bullish_reversal):
        quality = "coherent"
    elif bearish_reversal or bullish_reversal:
        quality = "fragmented"
    else:
        quality = "unclear"

    breakout_status = "none"
    for pattern in patterns:
        if pattern["name"] == "Range Breakout":
            breakout_status = "breakout" if pattern["direction"] == "bullish" else "breakdown"
            break
        if pattern["name"] in {"Spring", "Upthrust", "Liquidity Sweep"}:
            breakout_status = "false_breakdown" if pattern["direction"] == "bullish" else "false_breakout"
            break

    volume_confirmation = _volume_confirmation(latest)
    confidence = 0.50
    if trend in {"ascending", "descending"}:
        confidence += 0.12
    if quality == "coherent":
        confidence += 0.10
    if top:
        confidence += min(float(top["confidence"]) * 0.15, 0.12)
    if volume_confirmation == "expanding":
        confidence += 0.05

    return {
        "trend": trend,
        "structure_quality": quality,
        "pattern": top["name"] if top else "none",
        "breakout_status": breakout_status,
        "support": round(float(support), 4) if support is not None else None,
        "resistance": round(float(resistance), 4) if resistance is not None else None,
        "volume_confirmation": volume_confirmation,
        "confidence": round(min(confidence, 0.92), 2),
        "signals": [p["name"] for p in patterns[:5]],
    }


def _long_term_structure(
    df: pd.DataFrame,
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    patterns: list[dict[str, Any]],
) -> dict[str, Any]:
    latest = df.iloc[-1]
    close = float(latest["Close"])
    sma20 = latest.get("sma20")
    sma50 = latest.get("sma50")
    sma200 = latest.get("sma200")
    sma20 = float(sma20) if pd.notna(sma20) else None
    sma50 = float(sma50) if pd.notna(sma50) else None
    sma200 = float(sma200) if pd.notna(sma200) else None
    swing_trend = _swing_trend(highs[-6:], lows[-6:])

    if sma20 and sma50 and close > sma20 > sma50 and (sma200 is None or sma50 > sma200):
        trend = "ascending"
    elif sma20 and sma50 and close < sma20 < sma50 and (sma200 is None or sma50 < sma200):
        trend = "descending"
    elif swing_trend == "uptrend":
        trend = "ascending"
    elif swing_trend == "downtrend":
        trend = "descending"
    elif _is_consolidating(df.tail(60)):
        trend = "sideways"
    else:
        trend = "transition"

    bearish = [p for p in patterns if p["direction"] == "bearish" and p["confidence"] >= 0.62]
    bullish = [p for p in patterns if p["direction"] == "bullish" and p["confidence"] >= 0.62]
    if trend == "ascending":
        market_phase = "healthy_bull_trend"
        risk_state = "normal"
        if bearish:
            market_phase = "late_bull_distribution"
            risk_state = "elevated"
    elif trend == "descending":
        market_phase = "healthy_bear_trend"
        risk_state = "elevated"
        if bullish:
            market_phase = "early_bull_reversal"
            risk_state = "transition"
    elif trend == "sideways":
        market_phase = "range_compression"
        risk_state = "normal"
    else:
        market_phase = "unclear"
        risk_state = "transition"

    key_candidates = []
    if sma50:
        key_candidates.append(sma50)
    if sma200:
        key_candidates.append(sma200)
    key_candidates.extend(point.price for point in lows[-3:])
    key_level = _nearest_level_below(key_candidates, close)
    confidence = 0.58 + (0.12 if trend in {"ascending", "descending"} else 0.0)
    if sma50 and sma200:
        confidence += 0.06

    return {
        "trend": trend,
        "market_phase": market_phase,
        "key_level": round(float(key_level), 4) if key_level is not None else None,
        "risk_state": risk_state,
        "confidence": round(min(confidence, 0.88), 2),
    }


def _structure_conflicts(
    short: dict[str, Any],
    long: dict[str, Any],
    patterns: list[dict[str, Any]],
) -> list[str]:
    conflicts = []
    if short["trend"] != "unclear" and long["trend"] != "unclear" and short["trend"] != long["trend"]:
        conflicts.append(f"short-term trend {short['trend']} conflicts with long-term trend {long['trend']}")
    if short["trend"] == "ascending" and any(p["name"] in {"Shooting Star", "Bearish Engulfing", "Upthrust"} for p in patterns[:5]):
        conflicts.append("bearish rejection pattern appears inside short-term ascending structure")
    if short["trend"] == "descending" and any(p["name"] in {"Hammer", "Bullish Engulfing", "Spring"} for p in patterns[:5]):
        conflicts.append("bullish absorption pattern appears inside short-term descending structure")
    return conflicts


def _dominant_pattern(patterns: list[dict[str, Any]], categories: set[str]) -> Optional[dict[str, Any]]:
    for pattern in patterns:
        if pattern["category"] in categories:
            return pattern
    return None


def _volume_confirmation(row: pd.Series) -> str:
    ratio = float(row.get("volume_ratio20", 0.0))
    if ratio <= 0:
        return "unavailable"
    if ratio >= 1.5:
        return "expanding"
    if ratio < 0.7:
        return "shrinking"
    if ratio < 0.9:
        return "soft"
    return "normal"


def _latest_atr(df: pd.DataFrame) -> float:
    atr = df["atr14"].dropna()
    if not atr.empty:
        return float(atr.iloc[-1])
    recent = df.tail(min(14, len(df)))
    return float((recent["High"] - recent["Low"]).mean())


def _is_consolidating(df: pd.DataFrame) -> bool:
    if len(df) < 8:
        return False
    atr = _latest_atr(df)
    close = float(df["Close"].iloc[-1])
    if close <= 0:
        return False
    range_pct = float((df["High"].max() - df["Low"].min()) / close)
    return range_pct <= 0.06 or (atr > 0 and float(df["High"].max() - df["Low"].min()) <= 3.0 * atr)


def _swing_trend(highs: list[SwingPoint], lows: list[SwingPoint]) -> str:
    if len(highs) < 2 or len(lows) < 2:
        return "unclear"
    if highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price:
        return "uptrend"
    if highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price:
        return "downtrend"
    return "sideways"


def _near(left: float, right: float, tolerance_pct: float) -> bool:
    base = max(abs(left), abs(right), 1e-9)
    return abs(left - right) / base <= tolerance_pct


def _clustered(values: list[float], tolerance_pct: float) -> bool:
    if len(values) < 2:
        return False
    return (max(values) - min(values)) / max(_mean(values), 1e-9) <= tolerance_pct


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _nearest_level_below(levels: list[float], price: float) -> Optional[float]:
    below = [level for level in levels if level < price]
    return max(below) if below else None


def _nearest_level_above(levels: list[float], price: float) -> Optional[float]:
    above = [level for level in levels if level > price]
    return min(above) if above else None


def _dedupe_patterns(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for pattern in patterns:
        key = (pattern["name"], pattern.get("direction", "neutral"))
        current = best.get(key)
        if current is None or pattern["confidence"] > current["confidence"]:
            best[key] = pattern
    return list(best.values())
