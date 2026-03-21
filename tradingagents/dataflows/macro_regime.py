"""Macro regime classifier: risk-on / transition / risk-off."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf


# ---------------------------------------------------------------------------
# Signal thresholds
# ---------------------------------------------------------------------------

VIX_RISK_ON_THRESHOLD = 16.0    # VIX < 16 → risk-on
VIX_RISK_OFF_THRESHOLD = 25.0   # VIX > 25 → risk-off

REGIME_RISK_ON_THRESHOLD = 3    # score ≥ 3 → risk-on
REGIME_RISK_OFF_THRESHOLD = -3  # score ≤ -3 → risk-off

# Sector ETFs used for rotation signal
_DEFENSIVE_ETFS = ["XLU", "XLP", "XLV"]   # Utilities, Staples, Health Care
_CYCLICAL_ETFS = ["XLY", "XLK", "XLI"]    # Discretionary, Technology, Industrials


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download(symbols: list[str], period: str = "3mo") -> Optional[pd.DataFrame]:
    """Download closing prices, returning None on failure."""
    try:
        hist = yf.download(symbols, period=period, auto_adjust=True, progress=False, threads=True)
        if hist.empty:
            return None
        if len(symbols) == 1:
            closes = hist["Close"]
            if isinstance(closes, pd.DataFrame):
                closes = closes.iloc[:, 0]
            return closes.to_frame(name=symbols[0]).dropna()
        return hist["Close"].dropna(how="all")
    except Exception:
        return None


def _latest(series: pd.Series) -> Optional[float]:
    if series is None or series.empty:
        return None
    v = series.dropna()
    return float(v.iloc[-1]) if len(v) > 0 else None


def _sma(series: pd.Series, window: int) -> Optional[float]:
    if series is None or len(series.dropna()) < window:
        return None
    return float(series.dropna().rolling(window).mean().iloc[-1])


def _pct_change_n(series: pd.Series, n: int) -> Optional[float]:
    s = series.dropna()
    if len(s) < n + 1:
        return None
    base = float(s.iloc[-(n + 1)])
    current = float(s.iloc[-1])
    if base == 0:
        return None
    return (current - base) / base * 100


def _fmt_pct(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    return f"{val:+.1f}%"


# ---------------------------------------------------------------------------
# Individual signal evaluators (each returns +1, 0, or -1)
# ---------------------------------------------------------------------------

def _signal_vix_level(vix_price: Optional[float]) -> tuple[int, str]:
    """VIX level: <16 risk-on (+1), >25 risk-off (-1), else transition (0)."""
    if vix_price is None:
        return 0, "VIX level: unavailable (neutral)"
    if vix_price < VIX_RISK_ON_THRESHOLD:
        return 1, f"VIX level: {vix_price:.1f} < {VIX_RISK_ON_THRESHOLD} → risk-on"
    if vix_price > VIX_RISK_OFF_THRESHOLD:
        return -1, f"VIX level: {vix_price:.1f} > {VIX_RISK_OFF_THRESHOLD} → risk-off"
    return 0, f"VIX level: {vix_price:.1f} (neutral zone {VIX_RISK_ON_THRESHOLD}–{VIX_RISK_OFF_THRESHOLD})"


def _signal_vix_trend(vix_series: Optional[pd.Series]) -> tuple[int, str]:
    """VIX 5-day SMA vs 20-day SMA: rising VIX = risk-off."""
    if vix_series is None or len(vix_series) < 21:
        return 0, "VIX trend: insufficient history (neutral)"
    sma5 = _sma(vix_series, 5)
    sma20 = _sma(vix_series, 20)
    if sma5 is None or sma20 is None:
        return 0, "VIX trend: insufficient history (neutral)"
    if sma5 < sma20:
        return 1, f"VIX trend: declining (SMA5={sma5:.1f} < SMA20={sma20:.1f}) → risk-on"
    if sma5 > sma20:
        return -1, f"VIX trend: rising (SMA5={sma5:.1f} > SMA20={sma20:.1f}) → risk-off"
    return 0, f"VIX trend: flat (SMA5={sma5:.1f} ≈ SMA20={sma20:.1f}) → neutral"


def _signal_credit_spread(hyg_series: Optional[pd.Series], lqd_series: Optional[pd.Series]) -> tuple[int, str]:
    """HYG/LQD ratio: declining ratio = credit spreads widening = risk-off."""
    if hyg_series is None or lqd_series is None:
        return 0, "Credit spread proxy (HYG/LQD): unavailable (neutral)"

    # Align on common dates
    hyg = hyg_series.dropna()
    lqd = lqd_series.dropna()
    common = hyg.index.intersection(lqd.index)
    if len(common) < 22:
        return 0, "Credit spread proxy: insufficient history (neutral)"

    hyg_c = hyg.loc[common]
    lqd_c = lqd.loc[common]
    ratio = hyg_c / lqd_c
    ratio_1m = _pct_change_n(ratio, 21)

    if ratio_1m is None:
        return 0, "Credit spread proxy: cannot compute 1-month change (neutral)"
    if ratio_1m > 0.5:
        return 1, f"Credit spread (HYG/LQD) 1M: {_fmt_pct(ratio_1m)} → improving (risk-on)"
    if ratio_1m < -0.5:
        return -1, f"Credit spread (HYG/LQD) 1M: {_fmt_pct(ratio_1m)} → deteriorating (risk-off)"
    return 0, f"Credit spread (HYG/LQD) 1M: {_fmt_pct(ratio_1m)} → stable (neutral)"


def _signal_yield_curve(tlt_series: Optional[pd.Series], shy_series: Optional[pd.Series]) -> tuple[int, str]:
    """TLT (20yr) vs SHY (1-3yr): TLT outperforming = flight to safety = risk-off."""
    if tlt_series is None or shy_series is None:
        return 0, "Yield curve proxy (TLT vs SHY): unavailable (neutral)"

    tlt = tlt_series.dropna()
    shy = shy_series.dropna()
    tlt_1m = _pct_change_n(tlt, 21)
    shy_1m = _pct_change_n(shy, 21)

    if tlt_1m is None or shy_1m is None:
        return 0, "Yield curve proxy: insufficient history (neutral)"

    spread = tlt_1m - shy_1m
    if spread > 1.0:
        return -1, f"Yield curve: TLT {_fmt_pct(tlt_1m)} vs SHY {_fmt_pct(shy_1m)} → flight to safety (risk-off)"
    if spread < -1.0:
        return 1, f"Yield curve: TLT {_fmt_pct(tlt_1m)} vs SHY {_fmt_pct(shy_1m)} → risk appetite (risk-on)"
    return 0, f"Yield curve: TLT {_fmt_pct(tlt_1m)} vs SHY {_fmt_pct(shy_1m)} → neutral"


def _signal_market_breadth(spx_series: Optional[pd.Series]) -> tuple[int, str]:
    """S&P 500 above/below 200-day SMA."""
    if spx_series is None:
        return 0, "Market breadth (SPX vs 200 SMA): unavailable (neutral)"
    spx = spx_series.dropna()
    sma200 = _sma(spx, 200)
    current = _latest(spx)
    if sma200 is None or current is None:
        return 0, "Market breadth: insufficient history (neutral)"
    pct_from_sma = (current - sma200) / sma200 * 100
    if current > sma200:
        return 1, f"Market breadth: SPX {pct_from_sma:+.1f}% above 200-SMA → risk-on"
    return -1, f"Market breadth: SPX {pct_from_sma:+.1f}% below 200-SMA → risk-off"


def _signal_sector_rotation(
    defensive_closes: dict[str, pd.Series],
    cyclical_closes: dict[str, pd.Series],
) -> tuple[int, str]:
    """Defensive vs cyclical sector rotation over 1 month."""
    def avg_return(closes_dict: dict[str, pd.Series], days: int) -> Optional[float]:
        returns = []
        for sym, s in closes_dict.items():
            pct = _pct_change_n(s.dropna(), days)
            if pct is not None:
                returns.append(pct)
        return sum(returns) / len(returns) if returns else None

    def_ret = avg_return(defensive_closes, 21)
    cyc_ret = avg_return(cyclical_closes, 21)

    if def_ret is None or cyc_ret is None:
        return 0, "Sector rotation: unavailable (neutral)"

    spread = def_ret - cyc_ret
    if spread > 1.0:
        return -1, (
            f"Sector rotation: defensives {_fmt_pct(def_ret)} vs cyclicals {_fmt_pct(cyc_ret)} "
            f"(defensives leading → risk-off)"
        )
    if spread < -1.0:
        return 1, (
            f"Sector rotation: cyclicals {_fmt_pct(cyc_ret)} vs defensives {_fmt_pct(def_ret)} "
            f"(cyclicals leading → risk-on)"
        )
    return 0, (
        f"Sector rotation: defensives {_fmt_pct(def_ret)} vs cyclicals {_fmt_pct(cyc_ret)} → neutral"
    )


# ---------------------------------------------------------------------------
# Main classifier helpers
# ---------------------------------------------------------------------------

def _fetch_macro_data() -> tuple[
    Optional[pd.Series], Optional[pd.Series], Optional[pd.Series], Optional[pd.Series],
    Optional[pd.Series], Optional[pd.Series], dict[str, pd.Series], dict[str, pd.Series],
    Optional[float]
]:
    vix_data = _download(["^VIX"], period="3mo")
    market_data = _download(["^GSPC"], period="14mo")  # 14mo for 200-SMA
    hyg_lqd_data = _download(["HYG", "LQD"], period="3mo")
    tlt_shy_data = _download(["TLT", "SHY"], period="3mo")
    sector_data = _download(_DEFENSIVE_ETFS + _CYCLICAL_ETFS, period="3mo")

    # Extract series
    vix_series = vix_data["^VIX"] if vix_data is not None and "^VIX" in vix_data.columns else None
    spx_series = market_data["^GSPC"] if market_data is not None and "^GSPC" in market_data.columns else None
    hyg_series = (hyg_lqd_data["HYG"] if hyg_lqd_data is not None and "HYG" in hyg_lqd_data.columns else None)
    lqd_series = (hyg_lqd_data["LQD"] if hyg_lqd_data is not None and "LQD" in hyg_lqd_data.columns else None)
    tlt_series = (tlt_shy_data["TLT"] if tlt_shy_data is not None and "TLT" in tlt_shy_data.columns else None)
    shy_series = (tlt_shy_data["SHY"] if tlt_shy_data is not None and "SHY" in tlt_shy_data.columns else None)

    defensive_closes: dict[str, pd.Series] = {}
    cyclical_closes: dict[str, pd.Series] = {}
    if sector_data is not None:
        for sym in _DEFENSIVE_ETFS:
            if sym in sector_data.columns:
                defensive_closes[sym] = sector_data[sym]
        for sym in _CYCLICAL_ETFS:
            if sym in sector_data.columns:
                cyclical_closes[sym] = sector_data[sym]

    vix_price = _latest(vix_series)

    return (
        vix_series, spx_series, hyg_series, lqd_series, tlt_series, shy_series,
        defensive_closes, cyclical_closes, vix_price
    )


def _evaluate_signals(
    vix_price: Optional[float], vix_series: Optional[pd.Series],
    hyg_series: Optional[pd.Series], lqd_series: Optional[pd.Series],
    tlt_series: Optional[pd.Series], shy_series: Optional[pd.Series],
    spx_series: Optional[pd.Series], defensive_closes: dict[str, pd.Series],
    cyclical_closes: dict[str, pd.Series]
) -> tuple[int, list[dict]]:
    evaluators = [
        _signal_vix_level(vix_price),
        _signal_vix_trend(vix_series),
        _signal_credit_spread(hyg_series, lqd_series),
        _signal_yield_curve(tlt_series, shy_series),
        _signal_market_breadth(spx_series),
        _signal_sector_rotation(defensive_closes, cyclical_closes),
    ]

    signal_names = [
        "vix_level", "vix_trend", "credit_spread",
        "yield_curve", "market_breadth", "sector_rotation",
    ]

    signals = []
    total_score = 0
    for name, (score, description) in zip(signal_names, evaluators):
        signals.append({"name": name, "score": score, "description": description})
        total_score += score

    return total_score, signals


def _determine_regime_and_confidence(total_score: int) -> tuple[str, str]:
    if total_score >= REGIME_RISK_ON_THRESHOLD:
        regime = "risk-on"
    elif total_score <= REGIME_RISK_OFF_THRESHOLD:
        regime = "risk-off"
    else:
        regime = "transition"

    # Confidence based on how decisive the score is
    abs_score = abs(total_score)
    if abs_score >= 4:
        confidence = "high"
    elif abs_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return regime, confidence


def _generate_summary(
    regime: str, total_score: int, confidence: str, signals: list[dict], vix_price: Optional[float]
) -> str:
    risk_on_count = sum(1 for s in signals if s["score"] > 0)
    risk_off_count = sum(1 for s in signals if s["score"] < 0)
    neutral_count = sum(1 for s in signals if s["score"] == 0)

    summary = (
        f"Macro regime: **{regime.upper()}** "
        f"(score {total_score:+d}/6, confidence: {confidence}). "
        f"{risk_on_count} risk-on signals, {risk_off_count} risk-off signals, {neutral_count} neutral. "
        f"VIX: {vix_price:.1f}" if vix_price else
        f"Macro regime: **{regime.upper()}** "
        f"(score {total_score:+d}/6, confidence: {confidence}). "
        f"{risk_on_count} risk-on signals, {risk_off_count} risk-off signals, {neutral_count} neutral."
    )
    return summary


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------

def classify_macro_regime(curr_date: str = None) -> dict:
    """
    Classify current macro regime using 6 market signals.

    Args:
        curr_date: Optional reference date (informational only; always uses latest data)

    Returns:
        dict with keys:
            regime (str): "risk-on" | "transition" | "risk-off"
            score (int): Sum of signal scores (-6 to +6)
            confidence (str): "high" | "medium" | "low"
            signals (list[dict]): Per-signal breakdowns
            summary (str): Human-readable summary
    """
    # --- Download all required data ---
    (
        vix_series, spx_series, hyg_series, lqd_series, tlt_series, shy_series,
        defensive_closes, cyclical_closes, vix_price
    ) = _fetch_macro_data()

    # --- Evaluate each signal ---
    total_score, signals = _evaluate_signals(
        vix_price, vix_series, hyg_series, lqd_series, tlt_series, shy_series,
        spx_series, defensive_closes, cyclical_closes
    )

    # --- Classify regime ---
    regime, confidence = _determine_regime_and_confidence(total_score)

    summary = _generate_summary(regime, total_score, confidence, signals, vix_price)

    return {
        "regime": regime,
        "score": total_score,
        "confidence": confidence,
        "vix": vix_price,
        "signals": signals,
        "summary": summary,
    }


def format_macro_report(regime_data: dict) -> str:
    """Format classify_macro_regime output as a Markdown report."""
    regime = regime_data.get("regime", "unknown")
    score = regime_data.get("score", 0)
    confidence = regime_data.get("confidence", "unknown")
    vix = regime_data.get("vix")
    signals = regime_data.get("signals", [])
    summary = regime_data.get("summary", "")

    # Emoji-free regime indicator
    regime_display = regime.upper()

    lines = [
        "# Macro Regime Classification",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"## Regime: {regime_display}",
        "",
        "| Attribute | Value |",
        "|-----------|-------|",
        f"| Regime | **{regime_display}** |",
        f"| Composite Score | {score:+d} / 6 |",
        f"| Confidence | {confidence.title()} |",
        f"| VIX | {f'{vix:.2f}' if vix is not None else 'N/A'} |",
        "",
        "## Signal Breakdown",
        "",
        "| Signal | Score | Assessment |",
        "|--------|-------|------------|",
    ]

    score_labels = {1: "+1 (risk-on)", 0: " 0 (neutral)", -1: "-1 (risk-off)"}
    for sig in signals:
        score_label = score_labels.get(sig["score"], str(sig["score"]))
        lines.append(f"| {sig['name'].replace('_', ' ').title()} | {score_label} | {sig['description']} |")

    lines += [
        "",
        "## Interpretation",
        "",
        summary,
        "",
        "### What This Means for Trading",
        "",
    ]

    if regime == "risk-on":
        lines += [
            "- **Prefer:** Growth, cyclicals, small-caps, high-beta equities",
            "- **Reduce:** Defensive sectors, cash, long-duration bonds",
            "- **Technicals:** Favour breakout entries; momentum strategies work well",
        ]
    elif regime == "risk-off":
        lines += [
            "- **Prefer:** Defensive sectors (utilities, staples, healthcare), quality, low-beta",
            "- **Reduce:** Cyclicals, high-beta names, speculative positions",
            "- **Technicals:** Tighten stop-losses; favour mean-reversion over momentum",
        ]
    else:  # transition
        lines += [
            "- **Mixed signals:** No strong directional bias — size positions conservatively",
            "- **Watch:** Upcoming catalysts (FOMC, earnings, geopolitical events) may resolve direction",
            "- **Technicals:** Use wider stops; avoid overconfident entries",
        ]

    return "\n".join(lines)
