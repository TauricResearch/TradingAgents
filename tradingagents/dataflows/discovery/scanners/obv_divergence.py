"""OBV divergence scanner — detects multi-week accumulation via OBV/price divergence."""

from typing import Any, Dict, List, Optional

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


class OBVDivergenceScanner(BaseScanner):
    """Scan for OBV bullish divergence: price flat/falling while OBV trends up.

    Distinguishes multi-week institutional accumulation (sustained OBV rise
    during price consolidation) from the single-day spikes caught by the
    volume_accumulation scanner.
    """

    name = "obv_divergence"
    pipeline = "momentum"
    strategy = "volume_divergence"

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info("📈 Scanning OBV divergence (multi-week accumulation)...")

        lookback = self.scanner_config.get("lookback_days", 20)
        min_obv_pct = self.scanner_config.get("min_obv_pct_gain", 8.0)
        max_price_change = self.scanner_config.get("max_price_change_pct", 2.0)
        max_tickers = self.scanner_config.get("max_tickers", 2000)

        try:
            from tradingagents.dataflows.alpha_vantage_volume import (
                _records_to_dataframe,
                download_volume_data,
            )
            from tradingagents.dataflows.y_finance import _get_ticker_universe

            tickers = _get_ticker_universe(max_tickers=max_tickers)
            if not tickers:
                logger.info("No tickers in universe")
                return []

            # Reuse shared volume cache built by volume_accumulation scanner
            cache_key = self.scanner_config.get("volume_cache_key", "default")
            raw_data = download_volume_data(
                tickers=tickers,
                history_period_days=90,
                use_cache=True,
                cache_key=cache_key,
            )

            candidates = []
            for ticker, records in raw_data.items():
                result = self._detect_divergence(
                    ticker, records, lookback, min_obv_pct, max_price_change, _records_to_dataframe
                )
                if result:
                    candidates.append(result)

            # Sort by OBV gain descending; strongest divergences first
            candidates.sort(key=lambda x: x.get("_obv_pct_gain", 0), reverse=True)

            # Strip internal sort key before returning
            final = []
            for c in candidates[: self.limit]:
                c.pop("_obv_pct_gain", None)
                final.append(c)

            logger.info(f"Found {len(final)} OBV divergence candidates")
            return final

        except Exception as e:
            logger.warning(f"⚠️  OBV divergence scan failed: {e}")
            return []

    def _detect_divergence(
        self,
        ticker: str,
        records: List[Dict],
        lookback: int,
        min_obv_pct: float,
        max_price_change: float,
        records_to_df,
    ) -> Optional[Dict[str, Any]]:
        """Compute OBV and detect bullish price/OBV divergence."""
        try:
            hist = records_to_df(records)
            if hist.empty or len(hist) < lookback + 5:
                return None

            closes = hist["Close"].values
            volumes = hist["Volume"].values

            # Compute OBV as cumulative sum
            obv = [0.0]
            for i in range(1, len(closes)):
                if closes[i] > closes[i - 1]:
                    obv.append(obv[-1] + volumes[i])
                elif closes[i] < closes[i - 1]:
                    obv.append(obv[-1] - volumes[i])
                else:
                    obv.append(obv[-1])

            current_obv = obv[-1]
            past_obv = obv[-(lookback + 1)]
            current_price = float(closes[-1])
            past_price = float(closes[-(lookback + 1)])

            if past_price <= 0:
                return None

            price_change_pct = ((current_price - past_price) / past_price) * 100

            # Skip clear distribution: price dropped hard
            if price_change_pct < -5.0:
                return None

            # Normalize OBV change by avg_vol × lookback to get a scale-free percentage
            avg_vol = float(hist["Volume"].mean())
            if avg_vol <= 0:
                return None

            obv_change = current_obv - past_obv
            obv_pct_gain = (obv_change / (avg_vol * lookback)) * 100

            # Bullish divergence: OBV rising while price flat or falling
            if price_change_pct <= max_price_change and obv_pct_gain >= min_obv_pct:
                if obv_pct_gain >= 20.0 and price_change_pct <= 0.0:
                    priority = Priority.HIGH.value
                else:
                    priority = Priority.MEDIUM.value

                return {
                    "ticker": ticker,
                    "source": self.name,
                    "context": (
                        f"OBV divergence: price {price_change_pct:+.1f}% over {lookback}d, "
                        f"OBV +{obv_pct_gain:.1f}% of avg vol — multi-week accumulation signal"
                    ),
                    "priority": priority,
                    "strategy": self.strategy,
                    "_obv_pct_gain": obv_pct_gain,
                }
        except Exception:
            pass
        return None


SCANNER_REGISTRY.register(OBVDivergenceScanner)
