"""Daily bars for scoring a backtest, with an on-disk cache.

Scoring needs the same price history every time it runs, and re-scoring is
supposed to be free. Fetched bars are therefore cached as CSV under the run
directory: the first scoring pass downloads, every later pass — a different
weight map, a new metric, a re-read of an old run — reads from disk and needs
no network at all.

These bars are only ever used to *score* decisions that have already been made.
They are not part of the agent's information set, so fetching the full window
up front is not look-ahead: the agent never sees this frame. The guard in
:mod:`~tradingagents.backtest.guard` polices what the agent itself may request.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from tradingagents.dataflows.symbol_utils import normalize_symbol, resolve_benchmark

logger = logging.getLogger(__name__)

# Extra calendar days fetched past the last decision date so a position opened
# on the final decision can still be marked, and the hit-rate horizon has bars
# to measure against.
SETTLEMENT_BUFFER_DAYS = 45


def _cache_path(cache_dir: Path, ticker: str, start: str, end: str) -> Path:
    from tradingagents.dataflows.utils import safe_ticker_component

    return cache_dir / f"{safe_ticker_component(ticker)}_{start}_{end}.csv"


def fetch_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Download daily ``Open``/``Close`` bars for ``ticker``.

    The symbol is normalised first (``XAUUSD`` to ``GC=F`` and so on), so the
    scored instrument is the one the analysis priced (#984).
    """
    import yfinance as yf

    history = yf.Ticker(normalize_symbol(ticker)).history(start=start, end=end)
    if history is None or history.empty:
        return pd.DataFrame(columns=["Open", "Close"], index=pd.DatetimeIndex([]))
    return history[["Open", "Close"]]


def load_prices(
    tickers: list[str],
    start: str,
    end: str,
    cache_dir: str | Path | None = None,
    fetcher=fetch_prices,
) -> dict[str, pd.DataFrame]:
    """Load bars for each ticker, using ``cache_dir`` when available.

    A ticker whose history cannot be fetched is omitted from the result with a
    warning rather than aborting: a delisted name among ten should cost that one
    sleeve, not the whole scorecard. ``fetcher`` is injectable so tests never
    touch the network.
    """
    window_end = (
        datetime.strptime(end, "%Y-%m-%d") + timedelta(days=SETTLEMENT_BUFFER_DAYS)
    ).strftime("%Y-%m-%d")

    cache = Path(cache_dir) if cache_dir else None
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)

    out: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        frame = _load_one(ticker, start, window_end, cache, fetcher)
        if frame is not None and not frame.empty:
            out[ticker] = frame
        else:
            logger.warning(
                "No price history for %s over %s..%s; it will be left out of the "
                "scorecard.", ticker, start, window_end,
            )
    return out


def _load_one(ticker, start, end, cache: Path | None, fetcher) -> pd.DataFrame | None:
    path = _cache_path(cache, ticker, start, end) if cache is not None else None

    if path is not None and path.exists():
        try:
            return pd.read_csv(path, index_col=0, parse_dates=True)
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            logger.warning("Ignoring unreadable price cache %s: %s", path, exc)

    try:
        frame = fetcher(ticker, start, end)
    except Exception as exc:  # noqa: BLE001 - one bad symbol must not end scoring
        logger.warning("Could not fetch prices for %s: %s", ticker, exc)
        return None

    if path is not None and frame is not None and not frame.empty:
        try:
            frame.to_csv(path)
        except OSError as exc:
            logger.warning("Could not write price cache %s: %s", path, exc)
    return frame


def benchmark_for(tickers: list[str], config: dict) -> str:
    """The single benchmark used for a run's alpha.

    A backtest reports one portfolio-level alpha, so it needs one index. The
    first ticker's benchmark is used, which is right for the common
    single-market run and documented in the scorecard for a mixed-market one —
    better than silently averaging indices from different currencies.
    """
    if not tickers:
        return "SPY"
    return resolve_benchmark(tickers[0], config)
