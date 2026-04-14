"""Sector rotation scanner — finds laggards in accelerating sectors."""

from typing import Any, Dict, List, Optional

import pandas as pd

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.dataflows.universe import load_universe
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

# SPDR Select Sector ETFs
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

class SectorRotationScanner(BaseScanner):
    """Detect sector momentum shifts and find laggards in accelerating sectors."""

    name = "sector_rotation"
    pipeline = "momentum"
    strategy = "sector_rotation"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.max_tickers = self.scanner_config.get("max_tickers", 100)
        self.min_sector_accel = self.scanner_config.get("min_sector_acceleration", 2.0)

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info("🔄 Scanning sector rotation...")

        from tradingagents.dataflows.y_finance import download_history, get_ticker_info

        # Step 1: Identify accelerating sectors
        try:
            etf_symbols = list(SECTOR_ETFS.keys())
            etf_data = download_history(
                etf_symbols, period="2mo", interval="1d", auto_adjust=True, progress=False
            )
        except Exception as e:
            logger.error(f"Failed to download sector ETF data: {e}")
            return []

        if etf_data is None or etf_data.empty:
            return []

        accelerating_sectors = self._find_accelerating_sectors(etf_data)
        if not accelerating_sectors:
            logger.info("No accelerating sectors detected")
            return []

        sector_names = [SECTOR_ETFS.get(etf, etf) for etf in accelerating_sectors]
        logger.info(f"Accelerating sectors: {', '.join(sector_names)}")

        # Step 2: Batch-download 5-day close prices for all candidate tickers at once.
        # This replaces the previous serial get_ticker_info() + download_history() loop
        # which made up to max_tickers individual HTTP requests and would time out.
        tickers = load_universe(self.config)
        if not tickers:
            return []

        tickers = tickers[: self.max_tickers]

        try:
            batch_hist = download_history(
                tickers, period="1mo", interval="1d", auto_adjust=True, progress=False
            )
        except Exception as e:
            logger.warning(f"Batch history download failed: {e}")
            return []

        if batch_hist is None or batch_hist.empty:
            return []

        # Calculate 5-day return for each ticker from the batch data
        ticker_returns: Dict[str, float] = {}
        for ticker in tickers:
            try:
                if isinstance(batch_hist.columns, pd.MultiIndex):
                    if ticker not in batch_hist.columns.get_level_values(1):
                        continue
                    close = batch_hist.xs(ticker, axis=1, level=1)["Close"].dropna()
                else:
                    close = batch_hist["Close"].dropna()
                if len(close) < 6:
                    continue
                ticker_returns[ticker] = (float(close.iloc[-1]) / float(close.iloc[-6]) - 1) * 100
            except Exception:
                continue

        # Step 3: Only call get_ticker_info() for laggard tickers (< 2% 5d move).
        # Sort by most-negative return first — best laggards checked before limit.
        laggards = [(t, r) for t, r in ticker_returns.items() if r <= 2.0]
        laggards.sort(key=lambda x: x[1])

        candidates = []
        api_calls = 0
        max_api_calls = self.limit * 3  # budget for get_ticker_info calls
        for ticker, ret_5d in laggards:
            if len(candidates) >= self.limit or api_calls >= max_api_calls:
                break

            api_calls += 1
            result = self._check_sector_laggard(ticker, accelerating_sectors, get_ticker_info)
            if result:
                result["stock_5d_return"] = round(ret_5d, 2)
                candidates.append(result)

        logger.info(f"Sector rotation: {len(candidates)} candidates")
        return candidates

    def _find_accelerating_sectors(self, data: pd.DataFrame) -> List[str]:
        """Find sectors where 5-day return is accelerating vs 20-day trend."""
        accelerating = []

        for etf in SECTOR_ETFS:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if etf not in data.columns.get_level_values(1):
                        continue
                    close = data.xs(etf, axis=1, level=1)["Close"].dropna()
                else:
                    close = data["Close"].dropna()

                if len(close) < 21:
                    continue

                ret_5d = (float(close.iloc[-1]) / float(close.iloc[-6]) - 1) * 100
                ret_20d = (float(close.iloc[-1]) / float(close.iloc[-21]) - 1) * 100

                # Acceleration: 5-day annualized return significantly beats 20-day
                daily_rate_5d = ret_5d / 5
                daily_rate_20d = ret_20d / 20

                if daily_rate_20d != 0:
                    acceleration = daily_rate_5d / daily_rate_20d
                elif daily_rate_5d > 0:
                    acceleration = 10.0  # Strong acceleration from flat
                else:
                    acceleration = 0

                if acceleration >= self.min_sector_accel and ret_5d > 0:
                    accelerating.append(etf)
                    logger.debug(
                        f"{etf} ({SECTOR_ETFS[etf]}): 5d={ret_5d:+.1f}%, "
                        f"20d={ret_20d:+.1f}%, accel={acceleration:.1f}x"
                    )
            except Exception as e:
                logger.debug(f"Error analyzing {etf}: {e}")

        return accelerating

    def _check_sector_laggard(
        self, ticker: str, accelerating_sectors: List[str], get_info_fn
    ) -> Optional[Dict[str, Any]]:
        """Check if stock is in an accelerating sector (sector lookup only — no price download)."""
        try:
            info = get_info_fn(ticker)
            if not info:
                return None

            stock_sector = info.get("sector", "")

            # Map stock sector to ETF
            sector_to_etf = {v: k for k, v in SECTOR_ETFS.items()}
            sector_etf = sector_to_etf.get(stock_sector)

            if not sector_etf or sector_etf not in accelerating_sectors:
                return None

            # 5-day return is filled in by the caller (batch-computed)
            context = f"Sector rotation: {stock_sector} sector accelerating, {ticker} lagging"

            return {
                "ticker": ticker,
                "source": self.name,
                "context": context,
                "priority": Priority.MEDIUM.value,
                "strategy": self.strategy,
                "sector": stock_sector,
                "sector_etf": sector_etf,
                "stock_5d_return": 0.0,  # overwritten by caller
            }

        except Exception as e:
            logger.debug(f"Sector check failed for {ticker}: {e}")
            return None


SCANNER_REGISTRY.register(SectorRotationScanner)
