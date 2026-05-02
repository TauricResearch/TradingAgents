"""Macro regime classifier: risk-on / transition / risk-off."""

from __future__ import annotations

import math
import re
from datetime import datetime
from io import StringIO

import pandas as pd
import requests

from tradingagents.default_config import get_env_value

from .alpha_vantage_common import AlphaVantageError, _make_api_request
from .stockstats_utils import safe_yf_download

# ---------------------------------------------------------------------------
# Signal thresholds
# ---------------------------------------------------------------------------

VIX_RISK_ON_THRESHOLD = 16.0  # VIX < 16 → risk-on
VIX_RISK_OFF_THRESHOLD = 25.0  # VIX > 25 → risk-off

REGIME_RISK_ON_THRESHOLD = 3  # score ≥ 3 → risk-on
REGIME_RISK_OFF_THRESHOLD = -3  # score ≤ -3 → risk-off

# Sector ETFs used for rotation signal
_DEFENSIVE_ETFS = ["XLU", "XLP", "XLV"]  # Utilities, Staples, Health Care
_CYCLICAL_ETFS = ["XLY", "XLK", "XLI"]  # Discretionary, Technology, Industrials


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env_float(key: str, default: float) -> float:
    raw = get_env_value(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value) or value <= 0:
        return default
    return value


def _download(
    symbols: list[str],
    period: str = "3mo",
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame | None:
    """Download closing prices, returning None on failure."""
    try:
        download_kwargs = {"auto_adjust": True, "progress": False}
        if start or end:
            hist = safe_yf_download(symbols, start=start, end=end, **download_kwargs)
        else:
            hist = safe_yf_download(symbols, period=period, **download_kwargs)
        if hist is None:
            return None
        if hist.empty:
            return None
        if len(symbols) == 1:
            closes = hist["Close"]
            if isinstance(closes, pd.DataFrame):
                closes = closes[closes.columns[0]]
            return closes.to_frame(name=symbols[0]).dropna()
        closes = hist["Close"]
        if isinstance(closes, pd.Series):
            closes = closes.to_frame(name=symbols[0])
        return closes.dropna(how="all")
    except Exception:
        return None


def _download_vix_from_finviz_vx_futures() -> tuple[float | None, str | None, float | None]:
    """Fetch VX futures direction from Finviz futures page.

    Returns:
        (change_1d_pct, source_symbol, vix_like_price)

    Notes:
        Finviz futures page does not expose a stable machine-readable VIX spot
        series in this code path, so this helper returns directional percentage
        context only and leaves the absolute VIX level as unavailable.
    """
    url = "https://finviz.com/futures_charts.ashx?t=VX&p=h"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=_env_float("TRADINGAGENTS_MACRO_REGIME_FINVIZ_TIMEOUT_SEC", 20.0),
        )
    except requests.RequestException:
        return None, None, None

    if response.status_code != 200:
        return None, None, None

    html = response.text
    html_lower = html.lower()
    if "access denied" in html_lower or "captcha" in html_lower:
        return None, None, None

    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    if "futures" not in title.lower() or "vix" not in title.lower():
        return None, None, None

    pct_matches = re.findall(r"[-+]?\d+(?:\.\d+)?%", html)
    if not pct_matches:
        return None, None, None

    try:
        change_1d_pct = float(pct_matches[0].replace("%", ""))
    except ValueError:
        return None, None, None

    return change_1d_pct, "VX", None


def _download_vix_proxy_from_alpha_vantage() -> tuple[float | None, str | None, float | None]:
    """Fetch VIX proxy direction from Alpha Vantage (VXX/VIXY).

    Returns:
        (change_1d_pct, source_symbol, proxy_price)
    """
    for symbol in ("VXX", "VIXY"):
        try:
            csv_text = _make_api_request(
                "TIME_SERIES_DAILY_ADJUSTED",
                {
                    "symbol": symbol,
                    "outputsize": "compact",
                    "datatype": "csv",
                },
            )
            if not isinstance(csv_text, str):
                continue

            df = pd.read_csv(StringIO(csv_text))
            if df.empty or len(df) < 2:
                continue

            close_col = "adjusted_close" if "adjusted_close" in df.columns else "close"
            if close_col not in df.columns:
                continue

            closes = pd.to_numeric(df[close_col], errors="coerce").dropna()
            if len(closes) < 2:
                continue

            latest = float(closes.iloc[0])
            prev = float(closes.iloc[1])
            if prev == 0:
                continue

            change_1d_pct = (latest - prev) / prev * 100
            return change_1d_pct, symbol, latest
        except (AlphaVantageError, ValueError, TypeError, pd.errors.ParserError):
            continue

    return None, None, None


def _latest(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    v = series.dropna()
    return float(v.iloc[-1]) if len(v) > 0 else None


def _sma(series: pd.Series, window: int) -> float | None:
    if series is None or len(series.dropna()) < window:
        return None
    return float(series.dropna().rolling(window).mean().iloc[-1])


def _pct_change_n(series: pd.Series, n: int) -> float | None:
    s = series.dropna()
    if len(s) < n + 1:
        return None
    base = float(s.iloc[-(n + 1)])
    current = float(s.iloc[-1])
    if base == 0:
        return None
    return (current - base) / base * 100


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val:+.1f}%"


def _parse_as_of_date(curr_date: str | None) -> pd.Timestamp | None:
    if curr_date is None:
        return None
    try:
        as_of_date = pd.Timestamp(curr_date).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid macro regime curr_date {curr_date!r}; expected YYYY-MM-DD."
        ) from exc
    if pd.isna(as_of_date):
        raise ValueError(
            f"Invalid macro regime curr_date {curr_date!r}; expected YYYY-MM-DD."
        )
    return as_of_date


def _require_dated_series(
    symbol: str,
    series: pd.Series | None,
    min_rows: int,
    curr_date: str | None,
) -> None:
    available_rows = 0 if series is None else len(series.dropna())
    if available_rows < min_rows:
        raise RuntimeError(
            f"Macro regime date-bounded data for {curr_date} is unavailable for {symbol}: "
            f"need at least {min_rows} rows, got {available_rows}."
        )


# ---------------------------------------------------------------------------
# Individual signal evaluators (each returns +1, 0, or -1)
# ---------------------------------------------------------------------------


def _signal_vix_level(vix_price: float | None) -> tuple[int, str]:
    """VIX level: <16 risk-on (+1), >25 risk-off (-1), else transition (0)."""
    if vix_price is None:
        return 0, "VIX level: unavailable (neutral)"
    if vix_price < VIX_RISK_ON_THRESHOLD:
        return 1, f"VIX level: {vix_price:.1f} < {VIX_RISK_ON_THRESHOLD} → risk-on"
    if vix_price > VIX_RISK_OFF_THRESHOLD:
        return -1, f"VIX level: {vix_price:.1f} > {VIX_RISK_OFF_THRESHOLD} → risk-off"
    return (
        0,
        f"VIX level: {vix_price:.1f} (neutral zone {VIX_RISK_ON_THRESHOLD}–{VIX_RISK_OFF_THRESHOLD})",
    )


def _signal_vix_trend(vix_series: pd.Series | None) -> tuple[int, str]:
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


def _signal_credit_spread(
    hyg_series: pd.Series | None, lqd_series: pd.Series | None
) -> tuple[int, str]:
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


def _signal_yield_curve(
    tlt_series: pd.Series | None, shy_series: pd.Series | None
) -> tuple[int, str]:
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
        return (
            -1,
            f"Yield curve: TLT {_fmt_pct(tlt_1m)} vs SHY {_fmt_pct(shy_1m)} → flight to safety (risk-off)",
        )
    if spread < -1.0:
        return (
            1,
            f"Yield curve: TLT {_fmt_pct(tlt_1m)} vs SHY {_fmt_pct(shy_1m)} → risk appetite (risk-on)",
        )
    return 0, f"Yield curve: TLT {_fmt_pct(tlt_1m)} vs SHY {_fmt_pct(shy_1m)} → neutral"


def _signal_market_breadth(spx_series: pd.Series | None) -> tuple[int, str]:
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

    def avg_return(closes_dict: dict[str, pd.Series], days: int) -> float | None:
        returns = []
        for _sym, s in closes_dict.items():
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
    pd.Series | None,
    pd.Series | None,
    pd.Series | None,
    pd.Series | None,
    pd.Series | None,
    pd.Series | None,
    dict[str, pd.Series],
    dict[str, pd.Series],
    float | None,
    str,
    float | None,
]:
    return _fetch_macro_data_for_date(None)


def _fetch_macro_data_for_date(curr_date: str | None = None) -> tuple[
    pd.Series | None,
    pd.Series | None,
    pd.Series | None,
    pd.Series | None,
    pd.Series | None,
    pd.Series | None,
    dict[str, pd.Series],
    dict[str, pd.Series],
    float | None,
    str,
    float | None,
]:
    as_of_date = _parse_as_of_date(curr_date)
    if as_of_date is None:
        vix_data = _download(["^VIX"], period="3mo")
        market_data = _download(["^GSPC"], period="14mo")  # 14mo for 200-SMA
        hyg_lqd_data = _download(["HYG", "LQD"], period="3mo")
        tlt_shy_data = _download(["TLT", "SHY"], period="3mo")
        sector_data = _download(_DEFENSIVE_ETFS + _CYCLICAL_ETFS, period="3mo")
    else:
        end = (as_of_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        start_3mo = (as_of_date - pd.DateOffset(months=3)).strftime("%Y-%m-%d")
        start_14mo = (as_of_date - pd.DateOffset(months=14)).strftime("%Y-%m-%d")
        vix_data = _download(["^VIX"], start=start_3mo, end=end)
        market_data = _download(["^GSPC"], start=start_14mo, end=end)
        hyg_lqd_data = _download(["HYG", "LQD"], start=start_3mo, end=end)
        tlt_shy_data = _download(["TLT", "SHY"], start=start_3mo, end=end)
        sector_data = _download(_DEFENSIVE_ETFS + _CYCLICAL_ETFS, start=start_3mo, end=end)

    # Extract series with validation
    vix_series = vix_data["^VIX"] if vix_data is not None and "^VIX" in vix_data.columns else None
    spx_series = (
        market_data["^GSPC"] if market_data is not None and "^GSPC" in market_data.columns else None
    )
    hyg_series = (
        hyg_lqd_data["HYG"] if hyg_lqd_data is not None and "HYG" in hyg_lqd_data.columns else None
    )
    lqd_series = (
        hyg_lqd_data["LQD"] if hyg_lqd_data is not None and "LQD" in hyg_lqd_data.columns else None
    )
    tlt_series = (
        tlt_shy_data["TLT"] if tlt_shy_data is not None and "TLT" in tlt_shy_data.columns else None
    )
    shy_series = (
        tlt_shy_data["SHY"] if tlt_shy_data is not None and "SHY" in tlt_shy_data.columns else None
    )

    defensive_closes: dict[str, pd.Series] = {}
    cyclical_closes: dict[str, pd.Series] = {}
    if sector_data is not None:
        for sym in _DEFENSIVE_ETFS:
            if sym in sector_data.columns:
                defensive_closes[sym] = sector_data[sym]
        for sym in _CYCLICAL_ETFS:
            if sym in sector_data.columns:
                cyclical_closes[sym] = sector_data[sym]

    # Extract VIX price with validation and fallback chain:
    # yfinance -> Alpha Vantage proxy -> Finviz VX futures.
    # Known issue: yfinance can occasionally return corrupted VIX values.
    vix_price = _latest(vix_series)
    yfinance_vix_corrupt = vix_price is not None and vix_price > 100
    vix_source = "yfinance:^VIX"
    vix_proxy_change_1d: float | None = None

    if as_of_date is not None:
        required_series = {
            "^VIX": (vix_series, 21),
            "^GSPC": (spx_series, 200),
            "HYG": (hyg_series, 22),
            "LQD": (lqd_series, 22),
            "TLT": (tlt_series, 22),
            "SHY": (shy_series, 22),
            **{symbol: (defensive_closes.get(symbol), 22) for symbol in _DEFENSIVE_ETFS},
            **{symbol: (cyclical_closes.get(symbol), 22) for symbol in _CYCLICAL_ETFS},
        }
        for symbol, (series, min_rows) in required_series.items():
            _require_dated_series(symbol, series, min_rows, curr_date)
        if vix_price is None:
            raise RuntimeError(f"Macro regime data for {curr_date} is missing ^VIX close.")
        if vix_price > 100:
            raise RuntimeError(
                f"Macro regime data for {curr_date} has implausible ^VIX close {vix_price:.2f}."
            )
        return (
            vix_series,
            spx_series,
            hyg_series,
            lqd_series,
            tlt_series,
            shy_series,
            defensive_closes,
            cyclical_closes,
            vix_price,
            vix_source,
            vix_proxy_change_1d,
        )

    if vix_series is None or yfinance_vix_corrupt:
        av_change_1d, av_symbol, av_price = _download_vix_proxy_from_alpha_vantage()
        if av_change_1d is not None and av_symbol is not None:
            vix_proxy_change_1d = av_change_1d
            vix_source = f"alpha_vantage:{av_symbol}"
            # VXX/VIXY are proxy products, not spot VIX.
            vix_price = None
            if av_price is not None:
                vix_series = pd.Series([av_price], index=[pd.Timestamp.utcnow()], name=av_symbol)
        else:
            finviz_change_1d, finviz_symbol, finviz_price = _download_vix_from_finviz_vx_futures()
            if finviz_change_1d is not None and finviz_symbol is not None:
                vix_proxy_change_1d = finviz_change_1d
                vix_source = f"finviz:{finviz_symbol}"
                # VX futures provide direction context but not the VIX spot level here.
                vix_price = None
                if finviz_price is not None:
                    vix_series = pd.Series(
                        [finviz_price], index=[pd.Timestamp.utcnow()], name=finviz_symbol
                    )
            elif yfinance_vix_corrupt:
                # No healthy fallback available.
                vix_price = None
                vix_source = "unavailable"

    return (
        vix_series,
        spx_series,
        hyg_series,
        lqd_series,
        tlt_series,
        shy_series,
        defensive_closes,
        cyclical_closes,
        vix_price,
        vix_source,
        vix_proxy_change_1d,
    )


def _evaluate_signals(
    vix_price: float | None,
    vix_series: pd.Series | None,
    hyg_series: pd.Series | None,
    lqd_series: pd.Series | None,
    tlt_series: pd.Series | None,
    shy_series: pd.Series | None,
    spx_series: pd.Series | None,
    defensive_closes: dict[str, pd.Series],
    cyclical_closes: dict[str, pd.Series],
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
        "vix_level",
        "vix_trend",
        "credit_spread",
        "yield_curve",
        "market_breadth",
        "sector_rotation",
    ]

    signals = []
    total_score = 0
    for name, (score, description) in zip(signal_names, evaluators, strict=False):
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
    regime: str,
    total_score: int,
    confidence: str,
    signals: list[dict],
    vix_price: float | None,
    vix_source: str,
    vix_proxy_change_1d: float | None,
) -> str:
    risk_on_count = sum(1 for s in signals if s["score"] > 0)
    risk_off_count = sum(1 for s in signals if s["score"] < 0)
    neutral_count = sum(1 for s in signals if s["score"] == 0)

    prefix = (
        f"Macro regime: **{regime.upper()}** "
        f"(score {total_score:+d}/6, confidence: {confidence}). "
        f"{risk_on_count} risk-on signals, {risk_off_count} risk-off signals, {neutral_count} neutral."
    )

    if vix_price is not None:
        summary = f"{prefix} VIX: {vix_price:.1f} ({vix_source})."
    elif vix_proxy_change_1d is not None:
        direction = "up" if vix_proxy_change_1d > 0 else "down"
        source_phrase = "VX futures trend" if vix_source.startswith("finviz:VX") else "proxy trend"
        summary = (
            f"{prefix} VIX level unavailable; using {source_phrase} from {vix_source}: "
            f"{direction} {abs(vix_proxy_change_1d):.1f}% vs previous day."
        )
    else:
        summary = f"{prefix} VIX level unavailable ({vix_source})."

    return summary


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------


def classify_macro_regime(curr_date: str | None = None) -> dict:
    """
    Classify current macro regime using 6 market signals.

    Args:
        curr_date: Optional deterministic as-of date. When provided, yfinance
            downloads are bounded to windows ending on that date and live
            fallback sources are disabled. When omitted, legacy latest-data
            behavior is preserved.

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
        vix_series,
        spx_series,
        hyg_series,
        lqd_series,
        tlt_series,
        shy_series,
        defensive_closes,
        cyclical_closes,
        vix_price,
        vix_source,
        vix_proxy_change_1d,
    ) = _fetch_macro_data_for_date(curr_date)

    # --- Evaluate each signal ---
    total_score, signals = _evaluate_signals(
        vix_price,
        vix_series,
        hyg_series,
        lqd_series,
        tlt_series,
        shy_series,
        spx_series,
        defensive_closes,
        cyclical_closes,
    )

    # --- Classify regime ---
    regime, confidence = _determine_regime_and_confidence(total_score)

    summary = _generate_summary(
        regime,
        total_score,
        confidence,
        signals,
        vix_price,
        vix_source,
        vix_proxy_change_1d,
    )

    return {
        "regime": regime,
        "score": total_score,
        "confidence": confidence,
        "vix": vix_price,
        "vix_source": vix_source,
        "vix_proxy_change_1d": vix_proxy_change_1d,
        "signals": signals,
        "summary": summary,
    }


def format_macro_report(regime_data: dict, report_date: str | None = None) -> str:
    """Format classify_macro_regime output as a Markdown report."""
    regime = regime_data.get("regime", "unknown")
    score = regime_data.get("score", 0)
    confidence = regime_data.get("confidence", "unknown")
    vix = regime_data.get("vix")
    vix_source = regime_data.get("vix_source", "unknown")
    vix_proxy_change_1d = regime_data.get("vix_proxy_change_1d")
    signals = regime_data.get("signals", [])
    summary = regime_data.get("summary", "")

    # Emoji-free regime indicator
    regime_display = regime.upper()

    lines = [
        "# Macro Regime Classification",
        f"# Data retrieved on: {report_date or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"## Regime: {regime_display}",
        "",
        "| Attribute | Value |",
        "|-----------|-------|",
        f"| Regime | **{regime_display}** |",
        f"| Composite Score | {score:+d} / 6 |",
        f"| Confidence | {confidence.title()} |",
        f"| VIX | {f'{vix:.2f}' if vix is not None else 'N/A'} |",
        f"| VIX Source | {vix_source} |",
        (
            f"| VIX Fallback 1D Change | {vix_proxy_change_1d:+.2f}% |"
            if vix_proxy_change_1d is not None
            else "| VIX Fallback 1D Change | N/A |"
        ),
        "",
        "## Signal Breakdown",
        "",
        "| Signal | Score | Assessment |",
        "|--------|-------|------------|",
    ]

    score_labels = {1: "+1 (risk-on)", 0: " 0 (neutral)", -1: "-1 (risk-off)"}
    for sig in signals:
        score_label = score_labels.get(sig["score"], str(sig["score"]))
        lines.append(
            f"| {sig['name'].replace('_', ' ').title()} | {score_label} | {sig['description']} |"
        )

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
