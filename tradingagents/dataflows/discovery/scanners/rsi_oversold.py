"""RSI(2) mean-reversion oversold-bounce scanner.

Based on Larry Connors' 2-period RSI strategy (backtested 25 years, 75-79% win
rate) and Lehmann (1990) academic evidence for short-term weekly return reversals
(+0.86% to +1.24% per week for prior-week losers).

Signal: RSI(2) < 10 AND price above 200-day SMA.
The 200-day SMA filter is the critical guard against catching falling knives —
in persistent downtrends RSI(2) can stay oversold for weeks. With the trend
filter in place, the signal captures temporary pullbacks within an ongoing uptrend.

Expected holding period: 3–7 days. Exit target: RSI(2) > 90 or close above 5-day SMA.

Research: docs/iterations/research/2026-04-15-rsi-mean-reversion.md
"""

from typing import Any, Dict, List, Optional

import pandas as pd

from tradingagents.dataflows.data_cache.ohlcv_cache import download_ohlcv_cached
from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.dataflows.universe import load_universe
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


class RSIOversoldScanner(BaseScanner):
    """Scan for stocks with RSI(2) deeply oversold while price remains above 200-day SMA.

    Contrarian mean-reversion signal — the only non-momentum scanner in the pipeline.
    Identifies short-term panic selloffs within broader uptrends where a 3–7 day bounce
    is statistically expected.

    Data requirement: ~210 trading days of OHLCV (200d SMA + RSI buffer).
    Cost: single batch yfinance download via shared OHLCV cache, zero per-ticker API calls.
    """

    name = "rsi_oversold"
    pipeline = "momentum"
    strategy = "mean_reversion_bounce"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.max_rsi = self.scanner_config.get("max_rsi", 10.0)
        self.sma_period = self.scanner_config.get("sma_period", 200)
        self.rsi_period = self.scanner_config.get("rsi_period", 2)
        self.min_price = self.scanner_config.get("min_price", 5.0)
        self.min_avg_volume = self.scanner_config.get("min_avg_volume", 100_000)
        self.vol_avg_days = self.scanner_config.get("vol_avg_days", 20)
        self.max_tickers = self.scanner_config.get("max_tickers", 0)  # 0 = no cap

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info(f"📉 Scanning RSI({self.rsi_period}) oversold bounce (RSI < {self.max_rsi})...")

        tickers = load_universe(self.config)
        if not tickers:
            logger.warning("No tickers loaded for RSI oversold scan")
            return []

        if self.max_tickers:
            tickers = tickers[: self.max_tickers]

        cache_dir = self.config.get("discovery", {}).get("ohlcv_cache_dir", "data/ohlcv_cache")
        logger.info(f"Loading OHLCV for {len(tickers)} tickers from cache...")
        data = download_ohlcv_cached(tickers, period="1y", cache_dir=cache_dir)

        if not data:
            return []

        candidates = []
        for ticker, df in data.items():
            result = self._check_rsi_oversold(df)
            if result:
                result["ticker"] = ticker
                candidates.append(result)

        # Sort by RSI ascending — most oversold (lowest RSI) gets highest rank
        candidates.sort(key=lambda c: c.get("_rsi_value", 99))
        # Strip internal sort key
        for c in candidates:
            c.pop("_rsi_value", None)

        candidates = candidates[: self.limit]
        logger.info(f"RSI oversold bounce: {len(candidates)} candidates")
        return candidates

    def _check_rsi_oversold(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Compute RSI(2) and 200-day SMA; return candidate dict if signal fires."""
        try:
            df = df.dropna(subset=["Close", "Volume"])

            # Need at least sma_period + rsi_period + a buffer
            min_rows = self.sma_period + self.rsi_period + 5
            if len(df) < min_rows:
                return None

            close = df["Close"]
            volume = df["Volume"]

            current_close = float(close.iloc[-1])

            # --- Liquidity gates ---
            avg_vol = float(volume.iloc[-(self.vol_avg_days + 1) : -1].mean())
            if avg_vol < self.min_avg_volume:
                return None
            if current_close < self.min_price:
                return None

            # --- 200-day SMA trend filter ---
            sma200 = float(close.iloc[-self.sma_period :].mean())
            if current_close <= sma200:
                return None  # Price below 200d SMA → falling knife risk, skip

            # --- RSI(2) calculation ---
            # Use the last rsi_period+1 closes to compute one RSI value
            rsi_window = close.iloc[-(self.rsi_period + 2) :].values
            if len(rsi_window) < self.rsi_period + 1:
                return None

            deltas = [rsi_window[i] - rsi_window[i - 1] for i in range(1, len(rsi_window))]
            gains = [max(d, 0.0) for d in deltas]
            losses = [abs(min(d, 0.0)) for d in deltas]

            avg_gain = sum(gains[-self.rsi_period :]) / self.rsi_period
            avg_loss = sum(losses[-self.rsi_period :]) / self.rsi_period

            if avg_loss == 0:
                rsi = 100.0  # No losses → not oversold
            else:
                rs = avg_gain / avg_loss
                rsi = 100.0 - (100.0 / (1.0 + rs))

            if rsi >= self.max_rsi:
                return None

            # --- Priority ---
            if rsi < 5.0:
                priority = Priority.CRITICAL.value
            elif rsi < 8.0:
                priority = Priority.HIGH.value
            else:
                priority = Priority.MEDIUM.value

            pct_above_sma = ((current_close - sma200) / sma200) * 100

            context = (
                f"RSI({self.rsi_period}) oversold at {rsi:.1f} | "
                f"Price ${current_close:.2f} above 200d SMA ${sma200:.2f} "
                f"(+{pct_above_sma:.1f}%) | "
                f"3-7d mean-reversion bounce setup"
            )

            return {
                "source": self.name,
                "context": context,
                "priority": priority,
                "strategy": self.strategy,
                "_rsi_value": round(rsi, 2),
            }

        except Exception as e:
            logger.debug(f"RSI oversold check failed: {e}")
            return None


SCANNER_REGISTRY.register(RSIOversoldScanner)
