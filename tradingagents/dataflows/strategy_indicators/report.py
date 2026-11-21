"""Strategy-indicator reports for the market analyst.

Loads the instrument's daily OHLCV (rows on or before the analysis date only),
runs one indicator from :mod:`calc` and renders it as Markdown.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from tradingagents.dataflows.errors import NoMarketDataError, VendorError
from tradingagents.dataflows.strategy_indicators import (
    calc,
    gom_order_flow,
    harmonic_scanner,
    jfts_forces,
    unirenko,
)
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.intraday import load_intraday
from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv

logger = logging.getLogger(__name__)

MIN_ROWS = 30
MAX_TABLE_ROWS = 30


@dataclass(frozen=True)
class Spec:
    title: str
    description: str
    compute: Callable[..., calc.Result]
    needs_benchmark: bool = False
    needs_intraday: bool = False  # computed from hourly bars (order flow)


STRATEGY_INDICATORS: dict[str, Spec] = {
    "vwap_bands": Spec(
        "VWAP and deviation bands",
        "Rolling 20-bar volume-weighted average price with ±1σ/±2σ bands, plus VWAPs anchored at the year "
        "start and at the last swing high and low. Use: fair-value reference, mean-reversion stretch "
        "(beyond ±2σ), and which side of the anchored VWAPs buyers or sellers are in control.",
        calc.compute_vwap_bands),
    "volume_profile": Spec(
        "Volume and TPO profile",
        "Volume-at-price and time-at-price (TPO) over the look-back window: point of control (POC), the 70% "
        "value area (VAL–VAH), high- and low-volume nodes, and POC migration against the previous window. "
        "Use: acceptance/rejection of value, support/resistance at POC and nodes.",
        calc.compute_volume_profile),
    "zigzag": Spec(
        "ZigZag swings and market structure",
        "Swing highs/lows that reversed by an adaptive threshold, labelled HH/HL/LH/LL. Use: objective trend "
        "structure, the size and age of the current leg.",
        calc.compute_zigzag),
    "relative_volume": Spec(
        "Relative volume (RVOL)",
        "Each bar's volume against the prior 20-bar average, plus up-day vs down-day volume. Use: confirm "
        "breakouts, spot accumulation or distribution.",
        calc.compute_relative_volume),
    "relative_strength": Spec(
        "Relative strength vs benchmark",
        "The instrument against its market benchmark (SPY; XU100.IS for Borsa Istanbul; BTC-USD for crypto): "
        "RS line, Mansfield RS and period excess returns. Use: leadership vs laggard.",
        calc.compute_relative_strength, needs_benchmark=True),
    "volume_delta": Spec(
        "Estimated volume delta",
        "Buying vs selling pressure estimated from each bar's close location × volume, with cumulative delta "
        "and price/delta divergence. Use: whether volume supports the move.",
        calc.compute_volume_delta),
    "pivots": Spec(
        "Pivot levels",
        "Classic floor pivots (P, R1–R3, S1–S3), Camarilla H3/H4/L3/L4 and range midpoints from the previous "
        "day, week and month. Use: intraday-to-swing support/resistance map.",
        calc.compute_pivots),
    "zero_lag_macd": Spec(
        "Zero-lag MACD",
        "MACD built from zero-lag EMAs (12/26/9) with crossovers. Use: earlier momentum turns than the "
        "standard MACD.",
        calc.compute_zero_lag_macd),
    "tma_bands": Spec(
        "TMA bands",
        "Triangular moving average (20) with ±2.5×ATR(20) bands, band position and slope. Use: smoothed trend and "
        "overextension.",
        calc.compute_tma_bands),
    "gaps": Spec(
        "Price gaps",
        "Unfilled and partly filled price gaps of the last year and gaps filled in the window. Use: magnets "
        "and support/resistance.",
        calc.compute_gaps),
    "untested_levels": Spec(
        "Untested swing levels",
        "Swing highs/lows of the last year that price has not traded back through. Use: untested "
        "support/resistance and liquidity pools.",
        calc.compute_untested_levels),
    "candlestick_patterns": Spec(
        "Candlestick patterns",
        "Doji, hammer/hanging man, shooting star/inverted hammer, engulfing, harami, piercing/dark cloud, "
        "morning/evening star, three soldiers/crows, with how each played out on this instrument before. "
        "Use: reversal/continuation timing at key levels.",
        calc.compute_candlestick_patterns),
    "fibonacci": Spec(
        "Fibonacci levels and confluence",
        "Retracements and extensions of the latest swing, and zones where levels from several swings "
        "cluster. Use: pullback targets and confluence support/resistance.",
        calc.compute_fibonacci),
    "supply_demand": Spec(
        "Supply and demand zones",
        "Base-and-departure zones still active (fresh or tested, not broken). Use: where institutional "
        "orders likely rested.",
        calc.compute_supply_demand),
    "harmonic_patterns": Spec(
        "Harmonic patterns",
        "Gartley, Bat, Butterfly, Crab and AB=CD found on the swing points, with the potential reversal "
        "zone (PRZ) of patterns whose D leg is still forming.",
        calc.compute_harmonic_patterns),
    "harmonic_scanner": Spec(
        "Harmonic pattern scanner (HPC-style)",
        "AB=CD, Bat, Butterfly, Gartley, Crab, Shark and 5-0 on the swing points, each confirmed, pending (D "
        "inside its reversal zone, reversal awaited) or potential (D leg forming), with PRZ, quality score, "
        "38.2%/61.8% AD targets, an invalidation stop and how earlier patterns played out on this instrument. "
        "Strict AB=CD in ATRs and overlap filtering follow HPC's options (clean-room: published ratios only). "
        "Use: reversal zones with defined targets and stop.",
        harmonic_scanner.compute_harmonic_scanner),
    "divergence": Spec(
        "RSI/MACD divergences",
        "Regular and hidden divergences between price swings and RSI(14)/MACD. Use: momentum exhaustion "
        "(regular) or trend continuation (hidden).",
        calc.compute_divergence),
    "dev_stops": Spec(
        "Deviation stops",
        "Volatility stops at the two-bar true range's mean + 0/1/2.2/3.6 standard deviations from the "
        "10-bar extreme close. Use: trailing stop and trend-health check.",
        calc.compute_dev_stops),
    "supertrend": Spec(
        "SuperTrend",
        "ATR(10)×3 SuperTrend with direction changes. Use: trend direction and trailing stop.",
        calc.compute_supertrend),
    "mtf_ichimoku": Spec(
        "Multi-timeframe Ichimoku",
        "Ichimoku cloud (9/26/52) on daily, weekly and monthly bars with a per-timeframe score and bias, a "
        "daily cloud entry with a Kijun trailing stop filtered by the weekly cloud, and Kijun ± 2/3/4×ATR(26) "
        "extensions (clean-room, after NinjaTrader's iMTF). Use: trend alignment across timeframes, trailing "
        "stop, and cloud/Kijun support and resistance.",
        calc.compute_mtf_ichimoku),
    "jfts_forces": Spec(
        "JFTS Forces (JFTS AutoTrader)",
        "The JFTS AutoTrader's market-forces set: bull/bear legs, an EMA filter of the recent leg extremes that "
        "doubles as the long/short stop, six leg patterns (0D, 1B, 2B, L, R, Rx) and candle-body volume "
        "pressure. A long (short) entry needs the high above (low below) the filter, a long (short) pattern "
        "and the stop on the right side of the close. Use: trend-pullback entries with a defined stop.",
        jfts_forces.compute_jfts_forces),
    "unirenko": Spec(
        "UniRenko bars and prior-day levels (EPyF-style)",
        "UniRenko bars built from the daily path: the open bar completes in its trend direction after one trend "
        "offset and turns after one reversal offset (0.5×/1.5×ATR(14)), with the up and down ends of the open "
        "bar, the current run of same-direction bars, the last turn and the prior day's high, low and open "
        "(clean-room equivalent of the EPyF Basic Pack candles and prior-day levels). Use: noise-filtered trend "
        "direction and the exact prices that would extend or turn it.",
        unirenko.compute_unirenko),
    "gom_order_flow": Spec(
        "Gom order flow footprint (Gom Pro Pack)",
        "Per-session footprint after the Gom Pro Pack's GomOrderFlowProValues: buys, sells and delta, intrabar "
        "min/max delta and which was touched last, the POC, diagonal imbalances (ratio ≥ 3), stacked-imbalance "
        "support/resistance zones, imbalances and unfinished auctions at the high and low, COT (delta since the "
        "high/low) and declining-volume reversals. Use: who was aggressive inside the day and where.",
        gom_order_flow.compute_order_flow, needs_intraday=True),
    "gom_order_flow_levels": Spec(
        "Gom order flow levels (Gom Pro Pack)",
        "After GomOrderFlowProLevels: naked POCs and unfinished auctions not yet revisited, and stacked-imbalance "
        "zones not yet crossed by a full candle, nearest five above and below the close. Use: magnets and "
        "order-flow support/resistance.",
        gom_order_flow.compute_order_flow_levels, needs_intraday=True),
    "gom_cumulative_delta": Spec(
        "Gom cumulative delta (Gom Pro Pack)",
        "After GomCD: cumulative delta as an OHLC series per session, its trend against price and divergences "
        "at 20-session extremes. Use: whether aggressive buying or selling confirms the price move.",
        gom_order_flow.compute_cumulative_delta, needs_intraday=True),
    "gom_market_profile": Spec(
        "Gom market profile levels (Gom Pro Pack)",
        "After GomMPProLevels: volume at price from hourly bars for the current and previous day, week and month: "
        "POC, 70% value area (VAL–VAH), VWAP, and high/low volume nodes. Use: value acceptance/rejection and "
        "VWAP/POC reference levels.",
        gom_order_flow.compute_market_profile, needs_intraday=True),
}

SUMMARY = "strategy_summary"
INDICATOR_NAMES: tuple[str, ...] = (SUMMARY, *STRATEGY_INDICATORS)


def benchmark_for(symbol: str) -> str:
    canonical = normalize_symbol(symbol).upper()
    if canonical.endswith(".IS"):
        return "XU100.IS"
    if canonical.endswith("-USD") or canonical.endswith("-USDT"):
        return "BTC-USD"
    return "SPY"


def load_bars(symbol: str, as_of_date: str) -> pd.DataFrame:
    """Daily bars on or before ``as_of_date``, cleaned for the calculations."""
    data = load_ohlcv(symbol, as_of_date)
    canonical = normalize_symbol(symbol)
    if data is None or data.empty:
        raise NoMarketDataError(symbol, canonical, "no price rows")
    df = data.copy()
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Date", "Open", "High", "Low", "Close"])
    # The cut-off again: this report is quoted as fact, so it does not trust its input.
    df = df[df["Date"] <= pd.to_datetime(as_of_date)]
    df = df.sort_values("Date").drop_duplicates("Date", keep="last").reset_index(drop=True)
    df["Volume"] = df["Volume"].fillna(0.0)
    if len(df) < MIN_ROWS:
        raise NoMarketDataError(
            symbol, canonical, f"only {len(df)} price rows on or before {as_of_date}; {MIN_ROWS} are needed"
        )
    return df


def _cell(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return calc.num(value)
    try:
        if pd.isna(value):
            return "N/A"
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):  # numpy scalar
        return _cell(value.item())
    return str(value).replace("|", "/")


def markdown_table(df: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(str(c) for c in df.columns) + " |",
             "|" + "|".join("---" for _ in df.columns) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return "\n".join(lines)


def _render(name: str, spec: Spec, symbol: str, df: pd.DataFrame, since: pd.Timestamp, result: calc.Result) -> str:
    lines = [f"## {spec.title} ({name}) for {symbol.upper()}",
             f"Daily bars through {calc.day(df['Date'].iloc[-1])}; events and rows listed from {calc.day(since)}.",
             "", f"**Reading:** {result.headline}", ""]
    lines += [f"- {k}: {v}" for k, v in result.facts]
    for title, table in result.tables:
        if table is None or table.empty:
            continue
        shown = table.tail(MAX_TABLE_ROWS)
        suffix = f" (latest {MAX_TABLE_ROWS} of {len(table)})" if len(table) > MAX_TABLE_ROWS else ""
        lines += ["", f"### {title}{suffix}", "", markdown_table(shown)]
    lines += ["", spec.description]
    lines += [f"Note: {n}" for n in result.notes]
    return "\n".join(lines)


def _run(name: str, symbol: str, df: pd.DataFrame, since: pd.Timestamp, as_of_date: str) -> calc.Result:
    spec = STRATEGY_INDICATORS[name]
    if spec.needs_benchmark:
        bench_symbol = benchmark_for(symbol)
        if normalize_symbol(symbol).upper() == bench_symbol:
            return calc.Result(f"{symbol.upper()} is its own benchmark; relative strength does not apply.")
        bench = load_bars(bench_symbol, as_of_date)
        return spec.compute(df, since, bench, bench_symbol)
    if spec.needs_intraday:
        return spec.compute(df, since, load_intraday(symbol, as_of_date))
    return spec.compute(df, since)


def _summary(symbol: str, df: pd.DataFrame, since: pd.Timestamp, as_of_date: str) -> str:
    rows = []
    for name in STRATEGY_INDICATORS:
        try:
            reading = _run(name, symbol, df, since, as_of_date).headline
        except VendorError as exc:
            reading = f"unavailable ({exc})"
        except Exception as exc:  # noqa: BLE001 — one failing indicator must not sink the summary
            logger.warning("strategy indicator %s failed for %s: %s", name, symbol, exc)
            reading = f"could not be computed ({type(exc).__name__})"
        rows.append({"Indicator": name, "Reading": reading})
    close = float(df["Close"].iloc[-1])
    lines = [f"## Strategy indicator summary for {symbol.upper()}",
             f"Daily bars through {calc.day(df['Date'].iloc[-1])} (close {calc.num(close)}); "
             f"events counted from {calc.day(since)}.", "",
             markdown_table(pd.DataFrame(rows)), "",
             "Each line is the headline of one indicator; call get_strategy_indicator with that name for its "
             "levels, tables and method. Quote levels from tool output only."]
    return "\n".join(lines)


def strategy_indicator_report(symbol: str, indicator: str, as_of_date: str, look_back_days: int = 60) -> str:
    """Render one strategy indicator (or the summary of all) as of ``as_of_date``.

    Raises ValueError for an unknown indicator name, and the data layer's
    VendorError subclasses when the price history cannot be read.
    """
    name = indicator.strip().lower()
    if name not in INDICATOR_NAMES:
        raise ValueError(f"Strategy indicator {indicator} is not supported. Please choose from: {list(INDICATOR_NAMES)}")
    df = load_bars(symbol, as_of_date)
    days = max(5, min(int(look_back_days or 60), 3650))
    since = df["Date"].iloc[-1] - pd.Timedelta(days=days)
    if name == SUMMARY:
        return _summary(symbol, df, since, as_of_date)
    spec = STRATEGY_INDICATORS[name]
    return _render(name, spec, symbol, df, since, _run(name, symbol, df, since, as_of_date))
