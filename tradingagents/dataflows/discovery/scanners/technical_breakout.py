"""Technical breakout scanner — volume-confirmed price breakouts."""

from typing import Any, Dict, List, Optional

import pandas as pd

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_TICKER_FILE = "data/tickers.txt"


def _load_tickers_from_file(path: str) -> List[str]:
    """Load ticker symbols from a text file."""
    try:
        with open(path) as f:
            tickers = [
                line.strip().upper()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
        if tickers:
            logger.info(f"Breakout scanner: loaded {len(tickers)} tickers from {path}")
            return tickers
    except FileNotFoundError:
        logger.warning(f"Ticker file not found: {path}")
    except Exception as e:
        logger.warning(f"Failed to load ticker file {path}: {e}")
    return []


class TechnicalBreakoutScanner(BaseScanner):
    """Scan for volume-confirmed technical breakouts."""

    name = "technical_breakout"
    pipeline = "momentum"
    strategy = "technical_breakout"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.ticker_file = self.scanner_config.get(
            "ticker_file",
            config.get("tickers_file", DEFAULT_TICKER_FILE),
        )
        self.max_tickers = self.scanner_config.get("max_tickers", 150)
        self.min_volume_multiple = self.scanner_config.get("min_volume_multiple", 2.0)
        self.lookback_days = self.scanner_config.get("lookback_days", 20)

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info("📈 Scanning for technical breakouts...")

        tickers = _load_tickers_from_file(self.ticker_file)
        if not tickers:
            logger.warning("No tickers loaded for breakout scan")
            return []

        tickers = tickers[: self.max_tickers]

        # Batch download OHLCV
        from tradingagents.dataflows.y_finance import download_history

        try:
            data = download_history(
                tickers,
                period="3mo",
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
        except Exception as e:
            logger.error(f"Batch download failed: {e}")
            return []

        if data is None or data.empty:
            return []

        candidates = []
        for ticker in tickers:
            result = self._check_breakout(ticker, data)
            if result:
                candidates.append(result)

        # Sort by strongest breakout signal, then limit
        candidates.sort(key=lambda c: c.get("volume_multiple", 0), reverse=True)
        candidates = candidates[: self.limit]
        logger.info(f"Technical breakouts: {len(candidates)} candidates")
        return candidates

    def _check_breakout(self, ticker: str, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Check if ticker has a volume-confirmed breakout."""
        try:
            # Extract single-ticker data from multi-ticker download
            if isinstance(data.columns, pd.MultiIndex):
                if ticker not in data.columns.get_level_values(1):
                    return None
                df = data.xs(ticker, axis=1, level=1).dropna()
            else:
                df = data.dropna()

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
