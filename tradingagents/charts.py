"""Static technical analysis chart generation."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

import pandas as pd

from tradingagents.dataflows.stockstats_utils import load_ohlcv


@dataclass(frozen=True)
class ChartArtifact:
    title: str
    path: Path
    description: str


def normalize_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV data into a chart-ready daily time series."""
    normalized = data.copy()
    if "Date" not in normalized.columns:
        normalized = normalized.reset_index().rename(columns={"index": "Date"})

    normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce")
    normalized = normalized.dropna(subset=["Date"])

    value_columns = ["Open", "High", "Low", "Close", "Volume"]
    for column in value_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.dropna(subset=["Close"])
    normalized = normalized.sort_values("Date").reset_index(drop=True)
    return normalized


def add_core_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Add common trend, momentum, volatility, and volume-confirmation series."""
    chart_data = normalize_ohlcv(data)
    close = chart_data["Close"]

    chart_data["SMA_50"] = close.rolling(window=50, min_periods=1).mean()
    chart_data["SMA_200"] = close.rolling(window=200, min_periods=1).mean()

    chart_data["BB_MID"] = close.rolling(window=20, min_periods=1).mean()
    bb_std = close.rolling(window=20, min_periods=2).std()
    chart_data["BB_UPPER"] = chart_data["BB_MID"] + (bb_std * 2)
    chart_data["BB_LOWER"] = chart_data["BB_MID"] - (bb_std * 2)

    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    chart_data["MACD"] = ema_12 - ema_26
    chart_data["MACD_SIGNAL"] = chart_data["MACD"].ewm(span=9, adjust=False).mean()
    chart_data["MACD_HIST"] = chart_data["MACD"] - chart_data["MACD_SIGNAL"]

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    average_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    average_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0, pd.NA)
    chart_data["RSI_14"] = 100 - (100 / (1 + relative_strength))
    chart_data.loc[(average_loss == 0) & average_gain.notna(), "RSI_14"] = 100
    chart_data["RSI_14"] = chart_data["RSI_14"].clip(lower=0, upper=100)

    return chart_data


def render_technical_chart(symbol: str, data: pd.DataFrame, output_path: Path) -> ChartArtifact:
    """Render the core technical chart pack to a static PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(output_path.parent / ".matplotlib"))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    chart_data = add_core_indicators(data)
    if chart_data.empty:
        raise ValueError(f"No chartable OHLCV data available for {symbol}")

    dates = chart_data["Date"]

    fig, axes = plt.subplots(
        4,
        1,
        figsize=(14, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [3.0, 1.0, 1.4, 1.2]},
    )
    fig.suptitle(f"{symbol.upper()} Technical Analysis", fontsize=16, fontweight="bold")

    price_ax, volume_ax, macd_ax, rsi_ax = axes

    price_ax.plot(dates, chart_data["Close"], label="Close", color="#1f2937", linewidth=1.7)
    price_ax.plot(dates, chart_data["SMA_50"], label="SMA 50", color="#2563eb", linewidth=1.1)
    price_ax.plot(dates, chart_data["SMA_200"], label="SMA 200", color="#dc2626", linewidth=1.1)
    price_ax.plot(dates, chart_data["BB_MID"], label="Bollinger Mid", color="#64748b", linewidth=0.9)
    price_ax.plot(dates, chart_data["BB_UPPER"], label="Bollinger Upper", color="#7c3aed", linewidth=0.8)
    price_ax.plot(dates, chart_data["BB_LOWER"], label="Bollinger Lower", color="#7c3aed", linewidth=0.8)
    price_ax.fill_between(
        dates,
        chart_data["BB_LOWER"].astype(float),
        chart_data["BB_UPPER"].astype(float),
        color="#ede9fe",
        alpha=0.35,
    )
    price_ax.set_ylabel("Price")
    price_ax.grid(True, alpha=0.25)
    price_ax.legend(loc="upper left", ncols=3, fontsize=8)

    volume_ax.bar(dates, chart_data.get("Volume", pd.Series(0, index=chart_data.index)), color="#94a3b8")
    volume_ax.set_ylabel("Volume")
    volume_ax.grid(True, axis="y", alpha=0.25)

    hist_colors = chart_data["MACD_HIST"].apply(lambda value: "#16a34a" if value >= 0 else "#dc2626")
    macd_ax.bar(dates, chart_data["MACD_HIST"], color=hist_colors, alpha=0.45, label="Histogram")
    macd_ax.plot(dates, chart_data["MACD"], label="MACD", color="#0f766e", linewidth=1.2)
    macd_ax.plot(dates, chart_data["MACD_SIGNAL"], label="Signal", color="#f97316", linewidth=1.2)
    macd_ax.axhline(0, color="#475569", linewidth=0.8)
    macd_ax.set_ylabel("MACD")
    macd_ax.grid(True, alpha=0.25)
    macd_ax.legend(loc="upper left", fontsize=8)

    rsi_ax.plot(dates, chart_data["RSI_14"], label="RSI 14", color="#0891b2", linewidth=1.2)
    rsi_ax.axhline(70, color="#dc2626", linestyle="--", linewidth=0.9)
    rsi_ax.axhline(30, color="#16a34a", linestyle="--", linewidth=0.9)
    rsi_ax.set_ylim(0, 100)
    rsi_ax.set_ylabel("RSI")
    rsi_ax.grid(True, alpha=0.25)

    rsi_ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    rsi_ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(rsi_ax.xaxis.get_major_locator()))
    fig.autofmt_xdate()
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return ChartArtifact(
        title=f"{symbol.upper()} Technical Analysis",
        path=output_path,
        description="Price trend with moving averages and Bollinger Bands, volume, MACD momentum, and RSI.",
    )


def generate_report_charts(
    symbol: str,
    trade_date: str,
    save_path: Path,
    lookback_days: int = 365,
) -> list[ChartArtifact]:
    """Generate static chart artifacts for a saved report."""
    data = load_ohlcv(symbol, trade_date)
    chart_data = normalize_ohlcv(data)
    cutoff = pd.to_datetime(trade_date) - pd.Timedelta(days=lookback_days)
    chart_data = chart_data[chart_data["Date"] >= cutoff]
    artifact = render_technical_chart(
        symbol,
        chart_data,
        save_path / "charts" / "technical-analysis.png",
    )
    return [artifact]
