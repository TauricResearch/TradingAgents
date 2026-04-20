"""Value strategy signal (§3.3).

Composite value score from Book-to-Market, Earnings/Price, and
Cash-Flow/Price ratios. High composite = deep value; low = expensive.

Reference: Kakushadze & Serur §3.3 — "Value"
"""

from __future__ import annotations

import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal


class ValueStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Best for identifying long-term mean reversion candidates. Tips: Value traps are common — always check cash flow and debt levels. Works best in rising-rate environments. Combine with quality metrics (ROE, debt/equity) to filter traps."

    name = "value"
    description = "Composite value score: B/M, E/P, CF/P"
    target_analysts = ["fundamentals"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        info = kwargs.get("info")
        if info is None:
            try:
                info = yf.Ticker(ticker).info
            except Exception:
                return self._neutral(ticker, date)

        if not info:
            return self._neutral(ticker, date)

        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or 0
        if price <= 0:
            return self._neutral(ticker, date)

        # Book-to-Market (B/M)
        book_ps = info.get("bookValue") or 0
        bm = book_ps / price if book_ps > 0 else 0.0

        # Earnings/Price (E/P) — inverse of trailing P/E
        trailing_eps = info.get("trailingEps") or 0
        ep = trailing_eps / price if trailing_eps != 0 else 0.0

        # Cash-Flow/Price (CF/P)
        ocf = info.get("operatingCashflow") or 0
        shares = info.get("sharesOutstanding") or 0
        cfp = (ocf / shares) / price if shares > 0 and ocf != 0 else 0.0

        # Count how many ratios we have
        components = {"B/M": bm, "E/P": ep, "CF/P": cfp}
        valid = {k: v for k, v in components.items() if v != 0.0}
        if not valid:
            return self._neutral(ticker, date)

        # Composite: equal-weight average of available ratios (each z-scored
        # relative to typical ranges would be ideal, but we use simple
        # percentile-style thresholds for single-stock context)
        composite = sum(valid.values()) / len(valid)

        # Signal: higher composite = cheaper (more value)
        if composite > 0.15:
            signal = "STRONG"
            label = "deep value"
        elif composite > 0.06:
            signal = "MODERATE"
            label = "value"
        elif composite > 0.02:
            signal = "WEAK"
            label = "fair"
        elif composite > 0:
            signal = "NEUTRAL"
            label = "growth-priced"
        else:
            signal = "NEGATIVE"
            label = "expensive/negative earnings"

        direction = "SUPPORTS" if composite > 0.06 else "CONTRADICTS" if composite < 0.02 else "NEUTRAL"

        parts = [f"{k}={v:.3f}" for k, v in components.items() if v != 0.0]
        value_label = f"{composite:.3f} ({label}) [{', '.join(parts)}]"

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
                "book_to_market": round(bm, 4),
                "earnings_to_price": round(ep, 4),
                "cashflow_to_price": round(cfp, 4),
                "components_used": len(valid),
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
