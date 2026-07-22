"""Deterministic per-agent trading signals (rules mode).

Each evidence agent sees only the indicator values its spec requests
(rendered as DataRefs); these functions turn exactly those values into a
directional vote — bullish / bearish / neutral — with a confidence and a
claim that cites the numbers. Standard, a-priori technical rules; nothing
here is fitted to a backtest window:

- moving-average structure (close vs SMA50/SMA200, golden/death posture)
- momentum (RSI 50-line with a neutral buffer zone, MACD line+histogram)
- short-horizon pressure (close vs EMA10), Bollinger midline posture
- stochastic K/D, CCI extremes, Supertrend flip state, quant trend slope

Agents whose inputs are bar patterns rather than numeric indicators
(Wyckoff, Elliott, order blocks, ...) return None and ABSTAIN in rules
mode — a rule engine that pretended to read Wyckoff would be fabricating
evidence. The consensus judge tallies whoever actually voted; ties and
neutral pluralities resolve to HOLD.
"""

from __future__ import annotations

# ADX below this = no trend worth trading; the rules-mode judge holds.
CHOP_ADX_THRESHOLD = 18.0
# |score ratio| below this = the agent's own inputs disagree → neutral.
NEUTRAL_BAND = 0.34


def evaluate_refs(refs: dict[str, float]) -> tuple[str, int, str] | None:
    """(direction, confidence, claim) from one agent's visible values, or
    None to abstain (no rule applies to these inputs)."""
    score = 0.0
    weight = 0.0
    drivers: list[str] = []
    close = refs.get("LAST_CLOSE")

    def vote(condition_up: bool | None, w: float, label_up: str,
             label_down: str) -> None:
        nonlocal score, weight
        if condition_up is None:
            return
        weight += w
        if condition_up:
            score += w
            drivers.append(label_up)
        else:
            score -= w
            drivers.append(label_down)

    sma50, sma200 = refs.get("SMA_50"), refs.get("SMA_200")
    if close is not None and sma50 is not None:
        vote(close > sma50, 1.0, "close above SMA50", "close below SMA50")
    if sma50 is not None and sma200 is not None:
        vote(sma50 > sma200, 0.5, "golden posture (SMA50>SMA200)",
             "death posture (SMA50<SMA200)")

    ema10 = refs.get("EMA_10")
    if close is not None and ema10 is not None:
        vote(close > ema10, 0.5, "close above EMA10", "close below EMA10")

    rsi = refs.get("RSI_14")
    if rsi is not None:
        if rsi >= 60:
            vote(True, 1.0, f"RSI {rsi:.0f} bullish", "")
        elif rsi <= 40:
            vote(False, 1.0, "", f"RSI {rsi:.0f} bearish")
        else:
            weight += 1.0  # inside the 40-60 buffer: momentum undecided
            drivers.append(f"RSI {rsi:.0f} neutral")

    macd, macd_sig = refs.get("MACD.macd"), refs.get("MACD.signal")
    hist = refs.get("MACD.histogram")
    if macd is not None and macd_sig is not None and hist is not None:
        if hist > 0 and macd > macd_sig:
            vote(True, 1.0, "MACD above signal with positive histogram", "")
        elif hist < 0 and macd < macd_sig:
            vote(False, 1.0, "", "MACD below signal with negative histogram")
        else:
            weight += 1.0
            drivers.append("MACD mixed")

    mid = refs.get("BOLL.middle")
    if close is not None and mid is not None:
        vote(close > mid, 0.5, "close above Bollinger midline",
             "close below Bollinger midline")

    k, d = refs.get("STOCH.k"), refs.get("STOCH.d")
    if k is not None and d is not None:
        if k > d and k < 80:
            vote(True, 0.5, f"stochastic K>{'D'} rising ({k:.0f})", "")
        elif k < d and k > 20:
            vote(False, 0.5, "", f"stochastic K<D falling ({k:.0f})")
        else:
            weight += 0.5
            drivers.append("stochastic at an extreme")

    cci = refs.get("CCI_14")
    if cci is not None:
        if cci > 100:
            vote(True, 0.5, f"CCI {cci:.0f} strong", "")
        elif cci < -100:
            vote(False, 0.5, "", f"CCI {cci:.0f} weak")
        else:
            weight += 0.5
            drivers.append("CCI mid-range")

    st_line = refs.get("SUPERTREND.line")
    if close is not None and st_line is not None:
        vote(close > st_line, 1.0, "Supertrend long state",
             "Supertrend short state")

    slope = refs.get("TREND_SLOPE_PCT")
    if slope is not None:
        r2 = refs.get("TREND_R2", 0.5)
        w = 1.0 * max(0.25, min(1.0, r2 * 2))
        vote(slope > 0, w, f"trend slope +{slope:.3f}%/bar",
             f"trend slope {slope:.3f}%/bar")

    zscore = refs.get("CLOSE_ZSCORE_50")
    if zscore is not None:
        if abs(zscore) > 1.0:
            vote(zscore > 0, 0.5, f"z-score {zscore:+.1f} above mean",
                 f"z-score {zscore:+.1f} below mean")
        else:
            weight += 0.5
            drivers.append("z-score near mean")

    if weight == 0:
        return None  # no numeric rule applies → abstain honestly

    ratio = score / weight
    direction = ("neutral" if abs(ratio) < NEUTRAL_BAND
                 else "bullish" if ratio > 0 else "bearish")
    confidence = int(round(50 + 35 * min(1.0, abs(ratio))))
    claim = ("Deterministic rules: " + "; ".join(drivers[:4]) +
             f" → {direction} ({ratio:+.2f} score).")
    return direction, confidence, claim


def adx_says_chop(adx_value: float | None,
                  threshold: float = CHOP_ADX_THRESHOLD) -> bool:
    """True when trend strength is too weak to trade (rules-mode judge
    holds regardless of the directional consensus). FAIL CLOSED: a missing
    ADX reading (warm-up, degenerate series) means trend strength cannot be
    confirmed, so no entry."""
    return adx_value is None or adx_value < threshold
