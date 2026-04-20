"""Implied Volatility strategy signal (§3.5).

Compares options-implied volatility to realized volatility. The IV premium
(IV - RV) serves as a sentiment proxy: high premium = market pricing in
more risk than recent history suggests (fear), negative premium = complacency.

Reference: Kakushadze & Serur §3.5 — "Volatility Trading"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

_ANNUALIZE = np.sqrt(252)


class ImpliedVolStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: IV > realized vol suggests options market expects a move — potential catalyst ahead. Tips: High IV alone is not directional. IV crush after earnings can hurt option positions. Use as risk sizing input. Combine with event calendar."

    name = "implied_vol"
    description = "Options IV vs realized vol premium/discount"
    target_analysts = ["risk"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        # --- Realized vol (60-day trailing) ---
        hist = kwargs.get("hist")
        if hist is None:
            end = pd.Timestamp(date)
            start = end - pd.DateOffset(days=120)
            hist = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
            )
        if hist.empty or len(hist) < 20:
            return self._neutral(ticker, date)

        returns = hist["Close"].pct_change().dropna()
        trail = returns.iloc[-min(60, len(returns)):]
        realized_vol = float(trail.std() * _ANNUALIZE)

        # --- Implied vol from nearest-expiry ATM options ---
        iv = self._fetch_iv(ticker)
        if iv is None:
            return self._neutral(ticker, date, realized_vol=realized_vol)

        # IV premium: positive = market pricing more risk than realized
        iv_premium = iv - realized_vol
        iv_ratio = iv / realized_vol if realized_vol > 0 else 1.0

        # Interpret
        if iv_premium > 0.10:
            signal, label, direction = "STRONG", "high fear premium", "CONTRADICTS"
        elif iv_premium > 0.03:
            signal, label, direction = "MODERATE", "elevated premium", "NEUTRAL"
        elif iv_premium > -0.03:
            signal, label, direction = "WEAK", "fair premium", "NEUTRAL"
        else:
            signal, label, direction = "NEGATIVE", "complacency discount", "CONTRADICTS"

        value_label = (
            f"IV {iv:.1%} vs RV {realized_vol:.1%} "
            f"(premium {iv_premium:+.1%}, ratio {iv_ratio:.2f}x) — {label}"
        )

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(iv_premium, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "implied_vol": round(iv, 4),
                "realized_vol": round(realized_vol, 4),
                "iv_premium": round(iv_premium, 4),
                "iv_ratio": round(iv_ratio, 4),
            },
        )

    def _fetch_iv(self, ticker: str) -> float | None:
        """Fetch ATM implied vol from nearest-expiry options chain."""
        try:
            tk = yf.Ticker(ticker)
            expirations = tk.options
            if not expirations:
                return None
            chain = tk.option_chain(expirations[0])
            calls = chain.calls
            if calls.empty:
                return None
            # ATM: closest strike to current price
            price = tk.fast_info.get("lastPrice") or tk.fast_info.get("previousClose", 0)
            if not price:
                return None
            calls = calls.copy()
            calls["dist"] = (calls["strike"] - price).abs()
            atm = calls.loc[calls["dist"].idxmin()]
            iv = atm.get("impliedVolatility")
            return float(iv) if iv and iv > 0 else None
        except Exception:
            return None

    def _neutral(self, ticker: str, date: str, realized_vol: float | None = None) -> StrategySignal:
        rv_label = f"RV {realized_vol:.1%}, " if realized_vol else ""
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0,
            value_label=f"{rv_label}IV unavailable (no options data)",
            direction="NEUTRAL",
            detail={"realized_vol": round(realized_vol, 4) if realized_vol else None},
        )
