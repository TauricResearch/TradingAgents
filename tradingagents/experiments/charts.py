from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


def render_technical_chart(data: pd.DataFrame, ticker: str, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(path.parent / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    frame = data.copy().tail(90)
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    close = frame["Close"]
    ema20 = close.ewm(span=20).mean()
    ema50 = close.ewm(span=50).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, float("nan"))))
    macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    signal = macd.ewm(span=9).mean()

    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1]})
    for index, (_, row) in enumerate(frame.iterrows()):
        color = "#228B5A" if row["Close"] >= row["Open"] else "#C4493D"
        axes[0].vlines(index, row["Low"], row["High"], color=color, linewidth=1)
        axes[0].add_patch(Rectangle((index - 0.3, min(row["Open"], row["Close"])), 0.6, abs(row["Close"] - row["Open"]) or 0.01, color=color))
    axes[0].plot(range(len(frame)), ema20, label="EMA 20", linewidth=1)
    axes[0].plot(range(len(frame)), ema50, label="EMA 50", linewidth=1)
    axes[0].set_title(f"{ticker} technical chart")
    axes[0].legend()
    axes[1].plot(range(len(frame)), rsi, color="#9A6A24")
    axes[1].axhline(70, color="#C4493D", linewidth=0.8)
    axes[1].axhline(30, color="#228B5A", linewidth=0.8)
    axes[1].set_ylabel("RSI")
    axes[2].plot(range(len(frame)), macd, label="MACD")
    axes[2].plot(range(len(frame)), signal, label="Signal")
    axes[2].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
