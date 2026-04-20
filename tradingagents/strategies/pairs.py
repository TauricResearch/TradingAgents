"""Pairs Trading strategy signal (§3.8).

Cointegration-based spread between a ticker and its most correlated
portfolio peer. Signals relative over/undervaluation within a pair.

Reference: Kakushadze & Serur §3.8 — "Pairs Trading"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

# Default peers by sector when portfolio_tickers not provided
SECTOR_PEERS: dict[str, list[str]] = {
    "Technology": ["MSFT", "AAPL", "GOOG", "NVDA", "META"],
    "Communication Services": ["GOOG", "META", "NFLX", "DIS"],
    "Consumer Cyclical": ["AMZN", "TSLA", "NKE", "HD"],
    "Consumer Defensive": ["PG", "KO", "PEP", "WMT"],
    "Energy": ["XOM", "CVX", "COP"],
    "Financial Services": ["JPM", "BAC", "GS", "V", "MA"],
    "Healthcare": ["JNJ", "UNH", "PFE", "LLY"],
    "Industrials": ["CAT", "HON", "UPS", "GE"],
}


class PairsStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Identifies relative value between correlated stocks. Tips: Cointegration can break down — monitor spread stability. Best for market-neutral positioning. Requires both legs to be liquid. Signal is relative, not absolute."

    name = "pairs"
    description = "Cointegration spread vs most correlated peer"
    target_analysts = ["research"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        end = pd.Timestamp(date)
        start = end - pd.DateOffset(months=12)
        start_str = start.strftime("%Y-%m-%d")
        end_str = (end + pd.DateOffset(days=1)).strftime("%Y-%m-%d")

        hist = kwargs.get("hist")
        if hist is None:
            hist = yf.Ticker(ticker).history(start=start_str, end=end_str)
        if hist.empty or len(hist) < 60:
            return self._neutral(ticker, date)

        # Build candidate peer list
        candidates = list(kwargs.get("portfolio_tickers") or [])
        if not candidates:
            try:
                sector = yf.Ticker(ticker).info.get("sector", "")
                candidates = SECTOR_PEERS.get(sector, [])
            except Exception:
                candidates = []
        candidates = [c for c in candidates if c != ticker]
        if not candidates:
            return self._neutral(ticker, date)

        # Batch download all peer histories in one call
        stock_close = hist["Close"]
        best_peer, best_corr, best_peer_close = None, -1.0, None
        peers = candidates[:10]

        try:
            peer_data = yf.download(peers, start=start_str, end=end_str, group_by="ticker", progress=False)
        except Exception:
            peer_data = pd.DataFrame()

        for peer in peers:
            try:
                if len(peers) == 1:
                    ph_close = peer_data["Close"]
                else:
                    ph_close = peer_data[peer]["Close"]
                ph_close = ph_close.dropna()
                if len(ph_close) < 60:
                    continue
                aligned = pd.DataFrame({"s": stock_close, "p": ph_close}).dropna()
                if len(aligned) < 60:
                    continue
                corr = float(aligned["s"].corr(aligned["p"]))
                if corr > best_corr:
                    best_corr = corr
                    best_peer = peer
                    best_peer_close = aligned["p"]
                    stock_close_aligned = aligned["s"]
            except Exception:
                continue

        if best_peer is None or best_corr < 0.5:
            return self._neutral(ticker, date)

        # Compute spread: log(stock) - beta * log(peer)
        log_s = np.log(stock_close_aligned.values)
        log_p = np.log(best_peer_close.values)

        # OLS: log_s = alpha + beta * log_p
        x = log_p
        y = log_s
        beta = float(np.cov(x, y)[0, 1] / np.var(x)) if np.var(x) > 0 else 1.0
        alpha = float(np.mean(y) - beta * np.mean(x))
        spread = y - (alpha + beta * x)

        # Z-score of current spread vs rolling window
        window = min(60, len(spread))
        spread_mean = float(np.mean(spread[-window:]))
        spread_std = float(np.std(spread[-window:]))
        z_score = float((spread[-1] - spread_mean) / spread_std) if spread_std > 0 else 0.0

        # Signal: positive z = stock expensive vs peer, negative = cheap
        if z_score > 2.0:
            signal = "STRONG"
            direction = "CONTRADICTS"  # stock overvalued vs peer
        elif z_score > 1.0:
            signal = "MODERATE"
            direction = "CONTRADICTS"
        elif z_score < -2.0:
            signal = "STRONG"
            direction = "SUPPORTS"  # stock undervalued vs peer
        elif z_score < -1.0:
            signal = "MODERATE"
            direction = "SUPPORTS"
        else:
            signal = "NEUTRAL"
            direction = "NEUTRAL"

        label = (
            f"Z={z_score:+.2f} vs {best_peer} (corr={best_corr:.2f}, β={beta:.2f})"
            + (" — cheap vs peer" if z_score < -1 else " — expensive vs peer" if z_score > 1 else "")
        )

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(z_score, 4),
            value_label=label,
            direction=direction,
            detail={
                "peer": best_peer,
                "correlation": round(best_corr, 4),
                "beta": round(beta, 4),
                "alpha": round(alpha, 6),
                "spread_z": round(z_score, 4),
                "spread_mean": round(spread_mean, 6),
                "spread_std": round(spread_std, 6),
                "n_days": len(spread),
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (no suitable peer found)",
            direction="NEUTRAL", detail={},
        )
