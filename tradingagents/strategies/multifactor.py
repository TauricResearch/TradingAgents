"""Multifactor Portfolio strategy signal (§3.6).

Combined momentum + value + quality + low-vol composite score.
Equal-weighted z-score combination of four factors:
  1. Momentum: 12-1 month return
  2. Value: composite B/M, E/P, CF/P
  3. Quality: ROE + gross margin stability
  4. Low-Vol: inverse realized volatility (low-vol anomaly)

Reference: Kakushadze & Serur §3.6 — "Multifactor Models"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

_ANNUALIZE = np.sqrt(252)


class MultifactorStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Composite signal — more robust than any single factor. Tips: When factors disagree (e.g. high momentum + poor value), confidence should be LOW. Strongest when 3+ factors align. Weight recent factor performance when interpreting."

    name = "multifactor"
    description = "Combined momentum + value + quality + low-vol composite"
    target_analysts = ["portfolio"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        end = pd.Timestamp(date)
        start = end - pd.DateOffset(months=13)
        try:
            tk = yf.Ticker(ticker)
            hist = kwargs.get("hist")
            if hist is None:
                hist = tk.history(
                    start=start.strftime("%Y-%m-%d"),
                    end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
                )
            info = kwargs.get("info") or tk.info
        except Exception:
            return self._neutral(ticker, date)

        if hist.empty or len(hist) < 22 or not info:
            return self._neutral(ticker, date)

        close = hist["Close"]
        factors = {}

        # 1. Momentum (12-1 month return)
        ret_12m = (close.iloc[-1] / close.iloc[-min(252, len(close))]) - 1 if len(close) >= 22 else 0
        ret_1m = (close.iloc[-1] / close.iloc[-min(22, len(close))]) - 1
        factors["momentum"] = float(ret_12m - ret_1m)

        # 2. Value (composite B/M, E/P, CF/P)
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or 0
        if price > 0:
            bm = (info.get("bookValue") or 0) / price
            eps = info.get("trailingEps") or 0
            ep = eps / price if eps else 0
            ocf = info.get("operatingCashflow") or 0
            shares = info.get("sharesOutstanding") or 0
            cfp = (ocf / shares) / price if shares and ocf else 0
            vals = [v for v in (bm, ep, cfp) if v != 0]
            factors["value"] = float(sum(vals) / len(vals)) if vals else 0.0
        else:
            factors["value"] = 0.0

        # 3. Quality (ROE + gross margin)
        roe = info.get("returnOnEquity") or 0
        gm = info.get("grossMargins") or 0
        quality_parts = [v for v in (roe, gm) if v != 0]
        factors["quality"] = float(sum(quality_parts) / len(quality_parts)) if quality_parts else 0.0

        # 4. Low-Vol (inverse realized vol — lower vol = higher score)
        returns = close.pct_change().dropna()
        if len(returns) >= 20:
            vol = float(returns.iloc[-min(60, len(returns)):].std() * _ANNUALIZE)
            factors["low_vol"] = -vol  # negate so low vol = high score
        else:
            factors["low_vol"] = 0.0

        # Composite: equal-weight average of normalized factors
        # Simple approach: scale each to roughly [-1, 1] range then average
        normed = {
            "momentum": np.clip(factors["momentum"] / 0.30, -1, 1),   # ±30% = ±1
            "value": np.clip(factors["value"] / 0.15, -1, 1),          # ±0.15 = ±1
            "quality": np.clip(factors["quality"] / 0.30, -1, 1),      # ±30% = ±1
            "low_vol": np.clip((factors["low_vol"] + 0.25) / 0.15, -1, 1),  # 10%-40% vol → [-1,1]
        }
        composite = float(np.mean(list(normed.values())))

        # Signal classification
        if composite > 0.4:
            signal, label = "STRONG", "strong multifactor"
        elif composite > 0.1:
            signal, label = "MODERATE", "positive multifactor"
        elif composite > -0.1:
            signal, label = "NEUTRAL", "neutral"
        elif composite > -0.4:
            signal, label = "WEAK", "weak multifactor"
        else:
            signal, label = "NEGATIVE", "negative multifactor"

        direction = "SUPPORTS" if composite > 0.1 else "CONTRADICTS" if composite < -0.1 else "NEUTRAL"

        # Build value label with factor breakdown
        parts = [f"mom={factors['momentum']:+.1%}", f"val={factors['value']:.3f}",
                 f"qual={factors['quality']:.1%}", f"vol={-factors['low_vol']:.1%}"]
        value_label = f"{composite:+.2f} ({label}) [{', '.join(parts)}]"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(composite, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "composite": round(composite, 4),
                "factors_raw": {k: round(v, 4) for k, v in factors.items()},
                "factors_normed": {k: round(v, 4) for k, v in normed.items()},
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
