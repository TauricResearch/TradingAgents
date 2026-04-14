"""Technical breakout scanner — volume-confirmed price breakouts."""

from typing import Any, Dict, List, Optional

import pandas as pd

from tradingagents.dataflows.data_cache.ohlcv_cache import download_ohlcv_cached
from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.dataflows.universe import load_universe
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


class TechnicalBreakoutScanner(BaseScanner):
    """Scan for volume-confirmed technical breakouts."""

    name = "technical_breakout"
    pipeline = "momentum"
    strategy = "technical_breakout"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.max_tickers = self.scanner_config.get("max_tickers", 150)
        self.min_volume_multiple = self.scanner_config.get("min_volume_multiple", 2.0)
        self.lookback_days = self.scanner_config.get("lookback_days", 20)

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info("📈 Scanning for technical breakouts...")

        tickers = load_universe(self.config)
        if not tickers:
            logger.warning("No tickers loaded for breakout scan")
            return []

        tickers = tickers[: self.max_tickers]

        cache_dir = self.config.get("discovery", {}).get("ohlcv_cache_dir", "data/ohlcv_cache")
        logger.info(f"Loading OHLCV for {len(tickers)} tickers from cache (3mo)...")
        data = download_ohlcv_cached(tickers, period="3mo", cache_dir=cache_dir)

        if not data:
            return []

        candidates = []
        for ticker, df in data.items():
            result = self._check_breakout(ticker, df)
            if result:
                candidates.append(result)

        # Sort by strongest breakout signal, then limit
        candidates.sort(key=lambda c: c.get("volume_multiple", 0), reverse=True)
        candidates = candidates[: self.limit]
        logger.info(f"Technical breakouts: {len(candidates)} candidates")
        return candidates

    def _check_breakout(self, ticker: str, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Check if ticker has a volume-confirmed breakout."""
        try:
            df = df.dropna()

            if len(df) < self.lookback_days + 5:
                return None

            close = df["Close"]
            volume = df["Volume"]
            high = df["High"]

            latest_close = float(close.iloc[-1])
            latest_vol = float(volume.iloc[-1])

            # 20-day lookback resistance (excluding last day)
            lookback_high = float(high.iloc[-(self.lookback_days + 1) : -1].max())

            # Average volume over lookback period
            avg_vol = float(volume.iloc[-(self.lookback_days + 1) : -1].mean())

            if avg_vol <= 0:
                return None

            vol_multiple = latest_vol / avg_vol

            # Breakout conditions:
            # 1. Price closed above the lookback-period high
            # 2. Volume is at least min_volume_multiple times average
            is_breakout = latest_close > lookback_high and vol_multiple >= self.min_volume_multiple

            if not is_breakout:
                return None

            # Check if near 52-week high for bonus
            if len(df) >= 252:
                high_52w = float(high.iloc[-252:].max())
            else:
                high_52w = float(high.max())
            near_52w_high = latest_close >= high_52w * 0.95

            # Priority
            if vol_multiple >= 3.0 and near_52w_high:
                priority = Priority.CRITICAL.value
            elif vol_multiple >= 3.0 or near_52w_high:
                priority = Priority.HIGH.value
            else:
                priority = Priority.MEDIUM.value

            breakout_pct = ((latest_close - lookback_high) / lookback_high) * 100

            context = (
                f"Breakout: closed {breakout_pct:+.1f}% above {self.lookback_days}d high "
                f"on {vol_multiple:.1f}x volume"
            )
            if near_52w_high:
                context += " | Near 52-week high"

            return {
                "ticker": ticker,
                "source": self.name,
                "context": context,
                "priority": priority,
                "strategy": self.strategy,
                "volume_multiple": round(vol_multiple, 2),
                "breakout_pct": round(breakout_pct, 2),
                "near_52w_high": near_52w_high,
            }

        except Exception as e:
            logger.debug(f"Breakout check failed for {ticker}: {e}")
            return None


SCANNER_REGISTRY.register(TechnicalBreakoutScanner)
