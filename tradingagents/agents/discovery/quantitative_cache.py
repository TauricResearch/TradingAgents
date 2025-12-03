import logging
from collections import OrderedDict
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 100

_price_data_cache: OrderedDict[str, tuple[pd.DataFrame, datetime]] = OrderedDict()


def get_cached_price_data(ticker: str) -> pd.DataFrame | None:
    if ticker not in _price_data_cache:
        return None

    df, timestamp = _price_data_cache[ticker]

    _price_data_cache.move_to_end(ticker)

    return df.copy()


def set_cached_price_data(ticker: str, data: pd.DataFrame) -> None:
    global _price_data_cache

    if ticker in _price_data_cache:
        _price_data_cache.move_to_end(ticker)
        _price_data_cache[ticker] = (data.copy(), datetime.now())
        return

    while len(_price_data_cache) >= MAX_CACHE_SIZE:
        _price_data_cache.popitem(last=False)

    _price_data_cache[ticker] = (data.copy(), datetime.now())
    logger.debug(
        "Cached price data for %s (cache size: %d)", ticker, len(_price_data_cache)
    )


def clear_run_cache() -> None:
    global _price_data_cache
    count = len(_price_data_cache)
    _price_data_cache.clear()
    logger.debug("Cleared run cache (%d entries removed)", count)
