"""Minervini Trend Template scanner — Stage 2 uptrend identification.

Identifies stocks in a confirmed Stage 2 uptrend using Mark Minervini's
6-condition trend template, then ranks survivors by an IBD-style Relative
Strength (RS) Rating computed within the scanned universe.

All computation is pure OHLCV math — zero per-ticker API calls during scan.
"""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from tradingagents.dataflows.data_cache.ohlcv_cache import download_ohlcv_cached
from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.dataflows.universe import load_universe
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


class MinerviniScanner(BaseScanner):
    """Scan for stocks in a confirmed Minervini Stage 2 uptrend.

    Applies Mark Minervini's 6-condition trend template to identify stocks
    with healthy price structure (above rising SMAs, well off lows, near highs),
    then ranks by an IBD-style RS Rating computed within the scanned universe.

    Data requirement: ~200+ trading days of OHLCV (uses 1y lookback by default).
    Cost: single batch yfinance download, zero per-ticker API calls.
    """

    name = "minervini"
    pipeline = "momentum"
    strategy = "minervini"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.min_rs_rating = self.scanner_config.get("min_rs_rating", 70)
        self.lookback_period = self.scanner_config.get("lookback_period", "1y")
        self.sma_200_slope_days = self.scanner_config.get("sma_200_slope_days", 20)
        self.min_pct_off_low = self.scanner_config.get("min_pct_off_low", 30)
        self.max_pct_from_high = self.scanner_config.get("max_pct_from_high", 25)
        self.max_tickers = self.scanner_config.get("max_tickers", 0)  # 0 = no cap

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info("📊 Scanning for Minervini Stage 2 uptrends...")

        tickers = load_universe(self.config)
        if not tickers:
            logger.warning("No tickers loaded for Minervini scan")
            return []

        if self.max_tickers and len(tickers) > self.max_tickers:
            logger.info(f"Limiting Minervini scan to {self.max_tickers}/{len(tickers)} tickers")
            tickers = tickers[: self.max_tickers]

        cache_dir = self.config.get("discovery", {}).get("ohlcv_cache_dir", "data/ohlcv_cache")
        logger.info(
            f"Loading OHLCV for {len(tickers)} tickers from cache ({self.lookback_period})..."
        )
        data = download_ohlcv_cached(tickers, period=self.lookback_period, cache_dir=cache_dir)

        if not data:
            logger.warning("Minervini scanner: no OHLCV data available")
            return []

        # Compute 12-month returns for RS Rating (need all tickers' data)
        universe_returns: Dict[str, float] = {}
        passing_tickers: List[Tuple[str, Dict[str, Any]]] = []

        for ticker in tickers:
            df = data.get(ticker)
            if df is None or df.empty:
                continue
            result = self._check_minervini_df(df)
            if result is not None:
                ticker_df, metrics = result
                ret = self._compute_return(ticker_df)
                if ret is not None:
                    universe_returns[ticker] = ret
                passing_tickers.append((ticker, metrics))

        # Also compute returns for tickers that DIDN'T pass (for RS percentile ranking)
        for ticker in tickers:
            if ticker not in universe_returns:
                df = data.get(ticker)
                if df is None or df.empty:
                    continue
                try:
                    ret = self._compute_return(df)
                    if ret is not None:
                        universe_returns[ticker] = ret
                except Exception:
                    continue

        # Compute RS ratings as percentile ranks within the universe
        if universe_returns:
            all_returns = list(universe_returns.values())
            all_returns_sorted = sorted(all_returns)
            n = len(all_returns_sorted)

            def percentile_rank(val: float) -> float:
                pos = sum(1 for r in all_returns_sorted if r <= val)
                return round((pos / n) * 100, 1)

            rs_ratings = {t: percentile_rank(r) for t, r in universe_returns.items()}
        else:
            rs_ratings = {}

        # Build final candidates: pass RS filter, sort, limit
        candidates = []
        for ticker, metrics in passing_tickers:
            rs_rating = rs_ratings.get(ticker, 0)
            if rs_rating < self.min_rs_rating:
                continue

            pct_off_low = metrics["pct_off_low"]
            pct_from_high = metrics["pct_from_high"]

            # Priority based on RS Rating
            if rs_rating >= 90:
                priority = Priority.CRITICAL.value
            elif rs_rating >= 80:
                priority = Priority.HIGH.value
            else:
                priority = Priority.MEDIUM.value

            context = (
                f"Minervini Stage 2: P>SMA50>SMA150>SMA200, "
                f"+{pct_off_low:.0f}% off 52w low, "
                f"within {pct_from_high:.0f}% of 52w high, "
                f"RS Rating {rs_rating:.0f}/100"
            )

            candidates.append(
                {
                    "ticker": ticker,
                    "source": self.name,
                    "context": context,
                    "priority": priority,
                    "strategy": self.strategy,
                    "rs_rating": rs_rating,
                    "pct_off_low": round(pct_off_low, 1),
                    "pct_from_high": round(pct_from_high, 1),
                    "sma_50": round(metrics["sma_50"], 2),
                    "sma_150": round(metrics["sma_150"], 2),
                    "sma_200": round(metrics["sma_200"], 2),
                }
            )

        # Sort by RS Rating descending, then limit
        candidates.sort(key=lambda c: c.get("rs_rating", 0), reverse=True)
        candidates = candidates[: self.limit]

        logger.info(
            f"Minervini scanner: {len(candidates)} Stage 2 candidates "
            f"(RS >= {self.min_rs_rating}) from {len(tickers)} tickers"
        )
        return candidates

    def _check_minervini_df(
        self, df: pd.DataFrame
    ) -> Optional[Tuple[pd.DataFrame, Dict[str, Any]]]:
        """Apply the 6-condition Minervini trend template to a pre-extracted ticker DataFrame.

        Returns (df, metrics) if all conditions pass, None otherwise.
        """
        try:
            df = df.dropna()

            # Need at least 200 rows for SMA200
            if len(df) < 200:
                return None

            close = df["Close"]

            sma_50 = float(close.rolling(50).mean().iloc[-1])
            sma_150 = float(close.rolling(150).mean().iloc[-1])
            sma_200 = float(close.rolling(200).mean().iloc[-1])
            sma_200_prev = float(close.rolling(200).mean().iloc[-self.sma_200_slope_days - 1])
            price = float(close.iloc[-1])

            low_52w = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())
            high_52w = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())

            if low_52w <= 0 or sma_50 <= 0 or sma_150 <= 0 or sma_200 <= 0:
                return None

            pct_off_low = ((price - low_52w) / low_52w) * 100
            pct_from_high = ((high_52w - price) / high_52w) * 100

            # Minervini's 6 conditions (all must pass)
            conditions = [
                price > sma_150 > sma_200,  # 1. Price > SMA150 > SMA200
                sma_150 > sma_200,  # 2. SMA150 above SMA200
                sma_200 > sma_200_prev,  # 3. SMA200 slope is rising
                price > sma_50,  # 4. Price above SMA50
                pct_off_low >= self.min_pct_off_low,  # 5. At least 30% off 52w low
                pct_from_high <= self.max_pct_from_high,  # 6. Within 25% of 52w high
            ]

            if not all(conditions):
                return None

            return df, {
                "sma_50": sma_50,
                "sma_150": sma_150,
                "sma_200": sma_200,
                "pct_off_low": pct_off_low,
                "pct_from_high": pct_from_high,
            }

        except Exception as e:
            logger.debug(f"Minervini check failed: {e}")
            return None

    def _compute_return(self, df: pd.DataFrame) -> Optional[float]:
        """Compute IBD-style 12-month return with recent-quarter double-weighting.

        Formula: (full_year_return * 2 + last_quarter_return) / 3
        This weights recent momentum more heavily, matching IBD's RS methodology.
        """
        try:
            close = df["Close"] if "Close" in df.columns else df.iloc[:, 0]
            close = close.dropna()
            if len(close) < 2:
                return None

            latest = float(close.iloc[-1])
            year_ago = float(close.iloc[0])
            quarter_ago = float(close.iloc[max(0, len(close) - 63)])

            if year_ago <= 0 or quarter_ago <= 0:
                return None

            full_year_ret = (latest - year_ago) / year_ago
            quarter_ret = (latest - quarter_ago) / quarter_ago

            # IBD weighting: recent quarter counts double
            return (full_year_ret * 2 + quarter_ret) / 3

        except Exception:
            return None


SCANNER_REGISTRY.register(MinerviniScanner)
