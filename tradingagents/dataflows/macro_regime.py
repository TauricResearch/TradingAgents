"""Macro regime classifier: risk-on / transition / risk-off."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf


VIX_RISK_ON_THRESHOLD = 16.0
VIX_RISK_OFF_THRESHOLD = 25.0
REGIME_RISK_ON_THRESHOLD = 3
REGIME_RISK_OFF_THRESHOLD = -3

_DEFENSIVE_ETFS = ["XLU", "XLP", "XLV"]
_CYCLICAL_ETFS = ["XLY", "XLK", "XLI"]


def _download(
    symbols: list[str],
    period: str = "3mo",
    curr_date: str = None,
) -> Optional[pd.DataFrame]:
    kwargs = {
        "auto_adjust": True,
        "progress": False,
        "threads": True,
    }
    if curr_date:
        months_back = int(period[:-2])
        end_ts = pd.Timestamp(curr_date) + pd.Timedelta(days=1)
        start_ts = pd.Timestamp(curr_date) - pd.DateOffset(months=months_back + 1)
        kwargs["start"] = start_ts.strftime("%Y-%m-%d")
        kwargs["end"] = end_ts.strftime("%Y-%m-%d")
    else:
        kwargs["period"] = period
    try:
        history = yf.download(symbols, **kwargs)
    except Exception:
        return None

    if history.empty:
        return None

    closes = history["Close"]
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=symbols[0])
    return closes.dropna(how="all")


def _latest(series: Optional[pd.Series]) -> Optional[float]:
    if series is None:
        return None
    clean = series.dropna()
    if clean.empty:
        return None
    return float(clean.iloc[-1])


def _sma(series: Optional[pd.Series], window: int) -> Optional[float]:
    if series is None:
        return None
    clean = series.dropna()
    if len(clean) < window:
        return None
    return float(clean.rolling(window).mean().iloc[-1])


def _pct_change_n(series: pd.Series, periods: int) -> Optional[float]:
    clean = series.dropna()
    if len(clean) < periods + 1:
        return None
    base = float(clean.iloc[-(periods + 1)])
    current = float(clean.iloc[-1])
    if base == 0:
        return None
    return (current - base) / base * 100


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _signal_vix_level(vix_price: Optional[float]) -> tuple[int, str]:
    if vix_price is None:
        return 0, "VIX level unavailable (neutral)"
    if vix_price < VIX_RISK_ON_THRESHOLD:
        return 1, f"VIX level {vix_price:.1f} is below {VIX_RISK_ON_THRESHOLD} (risk-on)"
    if vix_price > VIX_RISK_OFF_THRESHOLD:
        return -1, f"VIX level {vix_price:.1f} is above {VIX_RISK_OFF_THRESHOLD} (risk-off)"
    return 0, f"VIX level {vix_price:.1f} is in the neutral zone"


def _signal_vix_trend(vix_series: Optional[pd.Series]) -> tuple[int, str]:
    sma5 = _sma(vix_series, 5)
    sma20 = _sma(vix_series, 20)
    if sma5 is None or sma20 is None:
        return 0, "VIX trend unavailable (neutral)"
    if sma5 < sma20:
        return 1, "Falling VIX trend supports risk-on"
    if sma5 > sma20:
        return -1, "Rising VIX trend supports risk-off"
    return 0, "Flat VIX trend is neutral"


def _signal_credit_spread(
    hyg_series: Optional[pd.Series],
    lqd_series: Optional[pd.Series],
) -> tuple[int, str]:
    if hyg_series is None or lqd_series is None:
        return 0, "Credit spread proxy unavailable (neutral)"
    common = hyg_series.dropna().index.intersection(lqd_series.dropna().index)
    if len(common) < 22:
        return 0, "Credit spread proxy unavailable (neutral)"
    ratio = hyg_series.loc[common] / lqd_series.loc[common]
    ratio_change = _pct_change_n(ratio, 21)
    if ratio_change is None:
        return 0, "Credit spread proxy unavailable (neutral)"
    if ratio_change > 0.5:
        return 1, "Credit spread proxy improving supports risk-on"
    if ratio_change < -0.5:
        return -1, "Credit spread proxy deteriorating supports risk-off"
    return 0, "Credit spread proxy is neutral"


def _signal_yield_curve(
    tlt_series: Optional[pd.Series],
    shy_series: Optional[pd.Series],
) -> tuple[int, str]:
    if tlt_series is None or shy_series is None:
        return 0, "Yield curve proxy unavailable (neutral)"
    tlt_change = _pct_change_n(tlt_series, 21)
    shy_change = _pct_change_n(shy_series, 21)
    if tlt_change is None or shy_change is None:
        return 0, "Yield curve proxy unavailable (neutral)"
    spread = tlt_change - shy_change
    if spread > 1.0:
        return -1, "Flight to safety favors risk-off"
    if spread < -1.0:
        return 1, "Risk appetite in duration favors risk-on"
    return 0, "Yield curve proxy is neutral"


def _signal_market_breadth(spx_series: Optional[pd.Series]) -> tuple[int, str]:
    current = _latest(spx_series)
    sma200 = _sma(spx_series, 200)
    if current is None or sma200 is None:
        return 0, "Market breadth unavailable (neutral)"
    if current > sma200:
        return 1, "S&P 500 above 200-day average supports risk-on"
    return -1, "S&P 500 below 200-day average supports risk-off"


def _signal_sector_rotation(
    defensive_closes: dict[str, pd.Series],
    cyclical_closes: dict[str, pd.Series],
) -> tuple[int, str]:
    def _average_change(payload: dict[str, pd.Series]) -> Optional[float]:
        changes = [
            change
            for change in (_pct_change_n(series, 21) for series in payload.values())
            if change is not None
        ]
        if not changes:
            return None
        return sum(changes) / len(changes)

    defensive_change = _average_change(defensive_closes)
    cyclical_change = _average_change(cyclical_closes)
    if defensive_change is None or cyclical_change is None:
        return 0, "Sector rotation unavailable (neutral)"
    spread = defensive_change - cyclical_change
    if spread > 1.0:
        return -1, "Defensives leading cyclicals supports risk-off"
    if spread < -1.0:
        return 1, "Cyclicals leading defensives supports risk-on"
    return 0, "Sector rotation is neutral"


def classify_macro_regime(curr_date: str = None) -> dict:
    vix_data = _download(["^VIX"], period="3mo", curr_date=curr_date)
    market_data = _download(["^GSPC"], period="14mo", curr_date=curr_date)
    credit_data = _download(["HYG", "LQD"], period="3mo", curr_date=curr_date)
    yield_data = _download(["TLT", "SHY"], period="3mo", curr_date=curr_date)
    sector_data = _download(
        _DEFENSIVE_ETFS + _CYCLICAL_ETFS,
        period="3mo",
        curr_date=curr_date,
    )

    vix_series = vix_data["^VIX"] if vix_data is not None and "^VIX" in vix_data else None
    spx_series = market_data["^GSPC"] if market_data is not None and "^GSPC" in market_data else None
    hyg_series = credit_data["HYG"] if credit_data is not None and "HYG" in credit_data else None
    lqd_series = credit_data["LQD"] if credit_data is not None and "LQD" in credit_data else None
    tlt_series = yield_data["TLT"] if yield_data is not None and "TLT" in yield_data else None
    shy_series = yield_data["SHY"] if yield_data is not None and "SHY" in yield_data else None

    defensive = {
        symbol: sector_data[symbol]
        for symbol in _DEFENSIVE_ETFS
        if sector_data is not None and symbol in sector_data
    }
    cyclical = {
        symbol: sector_data[symbol]
        for symbol in _CYCLICAL_ETFS
        if sector_data is not None and symbol in sector_data
    }

    evaluations = [
        ("vix_level", _signal_vix_level(_latest(vix_series))),
        ("vix_trend", _signal_vix_trend(vix_series)),
        ("credit_spread", _signal_credit_spread(hyg_series, lqd_series)),
        ("yield_curve", _signal_yield_curve(tlt_series, shy_series)),
        ("market_breadth", _signal_market_breadth(spx_series)),
        ("sector_rotation", _signal_sector_rotation(defensive, cyclical)),
    ]

    signals = []
    score = 0
    for name, (signal_score, description) in evaluations:
        signals.append(
            {"name": name, "score": signal_score, "description": description}
        )
        score += signal_score

    if score >= REGIME_RISK_ON_THRESHOLD:
        regime = "risk-on"
    elif score <= REGIME_RISK_OFF_THRESHOLD:
        regime = "risk-off"
    else:
        regime = "transition"

    abs_score = abs(score)
    if abs_score >= 4:
        confidence = "high"
    elif abs_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "regime": regime,
        "score": score,
        "confidence": confidence,
        "signals": signals,
        "summary": (
            f"Macro regime: **{regime.upper()}** "
            f"(score {score:+d}/6, confidence: {confidence})."
        ),
    }


def format_macro_report(regime_data: dict) -> str:
    lines = [
        "# Macro Regime Classification",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"## Regime: {regime_data['regime'].upper()}",
        "",
        "| Attribute | Value |",
        "|-----------|-------|",
        f"| Regime | **{regime_data['regime'].upper()}** |",
        f"| Composite Score | {regime_data['score']:+d} / 6 |",
        f"| Confidence | {regime_data['confidence'].title()} |",
        "",
        "## Signal Breakdown",
        "",
        "| Signal | Score | Assessment |",
        "|--------|-------|------------|",
    ]

    labels = {1: "+1 (risk-on)", 0: "0 (neutral)", -1: "-1 (risk-off)"}
    for signal in regime_data["signals"]:
        lines.append(
            f"| {signal['name'].replace('_', ' ').title()} | "
            f"{labels[signal['score']]} | {signal['description']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            regime_data["summary"],
            "",
            "### What This Means for Trading",
            "",
        ]
    )

    if regime_data["regime"] == "risk-on":
        lines.extend(
            [
                "- Prefer growth and cyclicals when momentum is confirming.",
                "- Use breakouts and trend continuation setups more confidently.",
            ]
        )
    elif regime_data["regime"] == "risk-off":
        lines.extend(
            [
                "- Prefer defensive sectors and tighter risk controls.",
                "- Reduce exposure to high-beta and speculative setups.",
            ]
        )
    else:
        lines.extend(
            [
                "- Keep position sizes moderate while signals remain mixed.",
                "- Wait for catalysts or clearer trend confirmation.",
            ]
        )

    return "\n".join(lines)
