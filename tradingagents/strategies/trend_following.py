"""Multi-Asset Trend Following strategy signal (§4.6).

Computes momentum across asset classes (equities, bonds, commodities) to
determine the macro regime: risk-on (equities leading), risk-off (bonds
leading), or mixed. Uses time-series momentum (absolute returns) and
cross-sectional momentum (relative ranking) across ETF proxies.

Reference: Kakushadze & Serur §4.6 — "Multi-Asset Trend Following"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

# Asset class proxies
ASSETS: dict[str, str] = {
    "equities": "SPY",
    "bonds": "TLT",
    "gold": "GLD",
    "commodities": "DBC",
}

# Lookback windows (trading days) and weights
WINDOWS = {"1m": 22, "3m": 63, "6m": 126}
WEIGHTS = {"1m": 0.4, "3m": 0.35, "6m": 0.25}


def _momentum(close: pd.Series, days: int) -> float | None:
    if len(close) < days + 1:
        return None
    return float(close.iloc[-1] / close.iloc[-days - 1] - 1)


class TrendFollowingStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Multi-timeframe trend alignment = high conviction directional signal. Tips: Trend following underperforms in range-bound markets. Strongest when short, medium, and long-term trends agree. Use trailing stops, not fixed targets."

    name = "trend_following"
    description = "Cross-asset momentum for macro regime (risk-on/risk-off)"
    target_analysts = ["portfolio"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        end = pd.Timestamp(date) + pd.DateOffset(days=1)
        start = pd.Timestamp(date) - pd.DateOffset(months=8)

        try:
            symbols = list(ASSETS.values())
            data = yf.download(
                symbols,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
            )
            if data.empty:
                return self._neutral(ticker, date)
            close = data["Close"]
        except Exception:
            return self._neutral(ticker, date)

        # Compute weighted momentum per asset class
        asset_scores: dict[str, float] = {}
        asset_detail: dict[str, dict] = {}
        for asset_class, symbol in ASSETS.items():
            if symbol not in close.columns:
                continue
            series = close[symbol].dropna()
            if len(series) < 30:
                continue

            total_w = 0.0
            score = 0.0
            window_returns = {}
            for label, days in WINDOWS.items():
                ret = _momentum(series, days)
                if ret is not None:
                    score += ret * WEIGHTS[label]
                    total_w += WEIGHTS[label]
                    window_returns[label] = round(ret, 4)

            if total_w > 0:
                score /= total_w
                asset_scores[asset_class] = score
                asset_detail[asset_class] = {
                    "symbol": symbol,
                    "score": round(score, 4),
                    **{f"ret_{k}": v for k, v in window_returns.items()},
                }

        if not asset_scores:
            return self._neutral(ticker, date)

        # Determine regime from relative ranking
        eq_score = asset_scores.get("equities", 0)
        bond_score = asset_scores.get("bonds", 0)

        # Count assets with positive momentum
        positive = sum(1 for s in asset_scores.values() if s > 0)
        total = len(asset_scores)

        if eq_score > 0 and eq_score > bond_score and positive >= total / 2:
            regime = "RISK-ON"
            signal = "STRONG" if eq_score > 0.05 else "MODERATE"
            direction = "SUPPORTS"
        elif bond_score > 0 and bond_score > eq_score:
            regime = "RISK-OFF"
            signal = "NEGATIVE" if eq_score < -0.03 else "WEAK"
            direction = "CONTRADICTS"
        elif positive == 0:
            regime = "BROAD WEAKNESS"
            signal = "NEGATIVE"
            direction = "CONTRADICTS"
        else:
            regime = "MIXED"
            signal = "NEUTRAL"
            direction = "NEUTRAL"

        # Build label
        parts = [f"{ac}: {s:+.1%}" for ac, s in sorted(asset_scores.items())]
        value_label = f"{regime} | {' | '.join(parts)}"

        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal=signal, value=round(eq_score, 4), value_label=value_label,
            direction=direction,
            detail={
                "regime": regime,
                "assets": asset_detail,
                "positive_count": positive,
                "total_assets": total,
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
