"""ML signal scanner — surfaces high P(WIN) setups from a ticker universe.

Universe is loaded from a text file (one ticker per line, # comments allowed).
Default: data/tickers.txt. Override via config: discovery.scanners.ml_signal.ticker_file
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import pandas as pd

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.dataflows.universe import load_universe
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


class MLSignalScanner(BaseScanner):
    """Scan a ticker universe for high ML win-probability setups.

    Loads the trained LightGBM/TabPFN model, fetches recent OHLCV data
    for a universe of tickers, computes technical features, and returns
    candidates whose predicted P(WIN) exceeds a configurable threshold.

    Optimized for large universes (500+ tickers):
    - Single batch yfinance download (1 HTTP request)
    - Parallel feature computation via ThreadPoolExecutor
    - Market cap skipped by default (1 NaN feature out of 30)
    """

    name = "ml_signal"
    pipeline = "momentum"
    strategy = "ml_signal"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.min_win_prob = self.scanner_config.get("min_win_prob", 0.50)
        # "6mo" instead of "1y" — halves the yfinance payload for 500+ tickers,
        # which prevents the batch download from hanging on slow connections.
        self.lookback_period = self.scanner_config.get("lookback_period", "6mo")
        self.max_workers = self.scanner_config.get("max_workers", 8)
        self.fetch_market_cap = self.scanner_config.get("fetch_market_cap", False)

        # Load universe: explicit config list overrides the shared universe file
        if "ticker_universe" in self.scanner_config:
            self.universe = self.scanner_config["ticker_universe"]
        else:
            self.universe = load_universe(config)
            if not self.universe:
                logger.warning("No tickers loaded — ML scanner will be empty")

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info(
            f"Running ML signal scanner on {len(self.universe)} tickers "
            f"(min P(WIN) = {self.min_win_prob:.0%})..."
        )

        # 1. Load ML model
        predictor = self._load_predictor()
        if predictor is None:
            logger.warning("No ML model available — skipping ml_signal scanner")
            return []

        # 2. Batch-fetch OHLCV data (single HTTP request)
        ohlcv_by_ticker = self._fetch_universe_ohlcv()
        if not ohlcv_by_ticker:
            logger.warning("No OHLCV data fetched — skipping ml_signal scanner")
            return []

        # 3. Compute features and predict in parallel
        candidates = self._predict_universe(predictor, ohlcv_by_ticker)

        # 4. Sort by P(WIN) descending and apply limit
        candidates.sort(key=lambda c: c.get("ml_win_prob", 0), reverse=True)
        candidates = candidates[: self.limit]

        logger.info(
            f"ML signal scanner: {len(candidates)} candidates above "
            f"{self.min_win_prob:.0%} threshold (from {len(ohlcv_by_ticker)} tickers)"
        )

        # Log individual candidate results
        if candidates:
            header = (
                f"{'Ticker':<8} {'P(WIN)':>8} {'P(LOSS)':>9} {'Prediction':>12} {'Priority':>10}"
            )
            separator = "-" * len(header)
            lines = ["\n  ML Signal Scanner Results:", f"  {header}", f"  {separator}"]
            for c in candidates:
                lines.append(
                    f"  {c['ticker']:<8} {c.get('ml_win_prob', 0):>7.1%} "
                    f"{c.get('ml_loss_prob', 0):>9.1%} "
                    f"{c.get('ml_prediction', 'N/A'):>12} "
                    f"{c.get('priority', 'N/A'):>10}"
                )
            lines.append(f"  {separator}")
            logger.info("\n".join(lines))

        return candidates

    def _load_predictor(self):
        """Load the trained ML model."""
        try:
            from tradingagents.ml.predictor import MLPredictor

            return MLPredictor.load()
        except Exception as e:
            logger.warning(f"Failed to load ML predictor: {e}")
            return None

    def _fetch_universe_ohlcv(self) -> Dict[str, pd.DataFrame]:
        """Batch-fetch OHLCV data for the entire ticker universe in chunks.

        Downloads in chunks of 150 tickers so a single slow/failed chunk doesn't
        block the whole scanner.  This replaces the previous single-request approach
        which would hang on large universes (500+ tickers × 1y of data).
        """
        from tradingagents.dataflows.y_finance import download_history

        chunk_size = 150
        universe = self.universe
        result: Dict[str, pd.DataFrame] = {}

        chunks = [universe[i : i + chunk_size] for i in range(0, len(universe), chunk_size)]
        logger.info(
            f"Batch-downloading {len(universe)} tickers ({self.lookback_period}) "
            f"in {len(chunks)} chunks..."
        )

        for idx, chunk in enumerate(chunks):
            try:
                raw = download_history(
                    " ".join(chunk),
                    period=self.lookback_period,
                    auto_adjust=True,
                    progress=False,
                )

                if raw is None or raw.empty:
                    continue

                if isinstance(raw.columns, pd.MultiIndex):
                    tickers_in_data = raw.columns.get_level_values(1).unique()
                    for ticker in tickers_in_data:
                        try:
                            ticker_df = raw.xs(ticker, level=1, axis=1).copy().reset_index()
                            if len(ticker_df) > 0:
                                result[ticker] = ticker_df
                        except (KeyError, ValueError):
                            continue
                else:
                    # Single-ticker fallback
                    raw = raw.reset_index()
                    if chunk:
                        result[chunk[0]] = raw

            except Exception as e:
                logger.warning(f"Chunk {idx + 1}/{len(chunks)} download failed: {e}")
                continue

        logger.info(f"Fetched OHLCV for {len(result)} tickers")
        return result

    def _predict_universe(
        self, predictor, ohlcv_by_ticker: Dict[str, pd.DataFrame]
    ) -> List[Dict[str, Any]]:
        """Predict P(WIN) for all tickers using parallel feature computation."""
        candidates = []

        if self.max_workers <= 1 or len(ohlcv_by_ticker) <= 10:
            # Serial execution for small universes
            for ticker, ohlcv in ohlcv_by_ticker.items():
                result = self._predict_ticker(predictor, ticker, ohlcv)
                if result is not None:
                    candidates.append(result)
        else:
            # Parallel feature computation for large universes
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._predict_ticker, predictor, ticker, ohlcv): ticker
                    for ticker, ohlcv in ohlcv_by_ticker.items()
                }
                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=10)
                        if result is not None:
                            candidates.append(result)
                    except Exception as e:
                        ticker = futures[future]
                        logger.debug(f"{ticker}: prediction timed out or failed — {e}")

        return candidates

    def _predict_ticker(
        self, predictor, ticker: str, ohlcv: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """Compute features and predict P(WIN) for a single ticker."""
        try:
            from tradingagents.ml.feature_engineering import (
                MIN_HISTORY_ROWS,
                compute_features_single,
            )

            if len(ohlcv) < MIN_HISTORY_ROWS:
                return None

            # Market cap: skip by default for speed (1 NaN out of 30 features)
            market_cap = self._get_market_cap(ticker) if self.fetch_market_cap else None

            # Compute features for the most recent date
            latest_date = pd.to_datetime(ohlcv["Date"]).max().strftime("%Y-%m-%d")
            features = compute_features_single(ohlcv, latest_date, market_cap=market_cap)
            if features is None:
                return None

            # Run ML prediction
            prediction = predictor.predict(features)
            if prediction is None:
                return None

            win_prob = prediction.get("win_prob", 0)
            loss_prob = prediction.get("loss_prob", 0)

            if win_prob < self.min_win_prob:
                return None

            # Determine priority from P(WIN)
            if win_prob >= 0.65:
                priority = Priority.CRITICAL.value
            elif win_prob >= 0.55:
                priority = Priority.HIGH.value
            else:
                priority = Priority.MEDIUM.value

            return {
                "ticker": ticker,
                "source": self.name,
                "context": (
                    f"ML model: {win_prob:.0%} win probability, "
                    f"{loss_prob:.0%} loss probability "
                    f"({prediction.get('prediction', 'N/A')})"
                ),
                "priority": priority,
                "strategy": self.strategy,
                "ml_win_prob": win_prob,
                "ml_loss_prob": loss_prob,
                "ml_prediction": prediction.get("prediction", "N/A"),
            }

        except Exception as e:
            logger.debug(f"{ticker}: ML prediction failed — {e}")
            return None

    def _get_market_cap(self, ticker: str) -> Optional[float]:
        """Get market cap (best-effort, cached in memory for the scan)."""
        if not hasattr(self, "_market_cap_cache"):
            self._market_cap_cache: Dict[str, Optional[float]] = {}

        if ticker in self._market_cap_cache:
            return self._market_cap_cache[ticker]

        try:
            from tradingagents.dataflows.y_finance import get_ticker_info

            info = get_ticker_info(ticker)
            cap = info.get("marketCap")
            self._market_cap_cache[ticker] = cap
            return cap
        except Exception:
            self._market_cap_cache[ticker] = None
            return None


SCANNER_REGISTRY.register(MLSignalScanner)
