"""Quant Analyst: deterministic technical signals computed from price history.

Variation 4 of the experiment. The other analysts are LLM-driven and
qualitative; this node computes hard numbers (momentum, MA crossover,
realised vol, RSI) and injects them into the market_report so the
Trader and Portfolio Manager have a quantitative anchor that doesn't
drift across runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

import numpy as np
import yfinance as yf


def _compute_quant_signals(ticker: str, trade_date: str) -> Dict[str, Optional[float]]:
    try:
        end = datetime.strptime(trade_date, "%Y-%m-%d")
        start = end - timedelta(days=300)
        hist = yf.Ticker(ticker).history(start=start.strftime("%Y-%m-%d"), end=trade_date)
        if len(hist) < 50:
            return {}
        close = hist["Close"].astype(float)
        last = float(close.iloc[-1])
        ma50 = float(close.tail(50).mean())
        ma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
        mom_20d = float((close.iloc[-1] / close.iloc[-21] - 1.0)) if len(close) >= 21 else None
        mom_60d = float((close.iloc[-1] / close.iloc[-61] - 1.0)) if len(close) >= 61 else None
        returns = close.pct_change().dropna()
        vol_30d = float(returns.tail(30).std() * np.sqrt(252)) if len(returns) >= 30 else None

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = float(100 - 100 / (1 + rs.iloc[-1])) if not np.isnan(rs.iloc[-1]) else None

        return {
            "last_price": last,
            "ma50": ma50,
            "ma200": ma200,
            "momentum_20d": mom_20d,
            "momentum_60d": mom_60d,
            "vol_30d_annualised": vol_30d,
            "rsi_14d": rsi,
        }
    except Exception:
        return {}


def _render_signals(ticker: str, signals: Dict[str, Optional[float]]) -> str:
    if not signals:
        return f"\n\n## Quantitative Signals ({ticker})\n\n_Price data unavailable; no signals computed._\n"

    lines = [f"\n\n## Quantitative Signals ({ticker})\n"]
    last = signals.get("last_price")
    ma50 = signals.get("ma50")
    ma200 = signals.get("ma200")
    if last is not None:
        lines.append(f"- Last close: {last:.2f}")
    if ma50 is not None:
        rel = (last / ma50 - 1.0) if last else None
        lines.append(f"- 50-day MA: {ma50:.2f} (price is {rel:+.1%} vs MA)" if rel is not None else f"- 50-day MA: {ma50:.2f}")
    if ma200 is not None:
        rel = (last / ma200 - 1.0) if last else None
        lines.append(f"- 200-day MA: {ma200:.2f} (price is {rel:+.1%} vs MA)" if rel is not None else f"- 200-day MA: {ma200:.2f}")
        if ma50 is not None:
            cross = "above" if ma50 > ma200 else "below"
            lines.append(f"- MA50/MA200 regime: 50-day is **{cross}** 200-day ({'bullish' if cross == 'above' else 'bearish'} cross)")
    if signals.get("momentum_20d") is not None:
        lines.append(f"- 20-day momentum: {signals['momentum_20d']:+.1%}")
    if signals.get("momentum_60d") is not None:
        lines.append(f"- 60-day momentum: {signals['momentum_60d']:+.1%}")
    if signals.get("vol_30d_annualised") is not None:
        lines.append(f"- 30-day annualised volatility: {signals['vol_30d_annualised']:.1%}")
    if signals.get("rsi_14d") is not None:
        rsi = signals["rsi_14d"]
        zone = "overbought" if rsi > 70 else ("oversold" if rsi < 30 else "neutral")
        lines.append(f"- 14-day RSI: {rsi:.1f} ({zone})")
    return "\n".join(lines) + "\n"


def create_quant_analyst():
    """Return a graph node that appends a quant-signals block to market_report.

    No LLM is used; this is deterministic. The node still has the create_X
    factory shape for consistency with the rest of the agent surface.
    """

    def quant_node(state) -> dict:
        ticker = state["company_of_interest"]
        trade_date = state["trade_date"]
        signals = _compute_quant_signals(ticker, trade_date)
        block = _render_signals(ticker, signals)
        existing = state.get("market_report", "") or ""
        return {"market_report": existing + block}

    return quant_node
