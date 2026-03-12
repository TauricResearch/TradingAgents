"""Universe builder for stock screening.

Builds the initial stock universe from KRX or US markets,
filtered by basic criteria (market cap, volume).
"""

import logging

import pandas as pd

from tradingagents.dataflows.screening_data import get_krx_universe, get_us_universe

logger = logging.getLogger(__name__)


def build_universe(config: dict) -> pd.DataFrame:
    """Build stock universe based on config settings.

    Args:
        config: Trading config with market, screening, and universe settings.

    Returns:
        DataFrame with columns: Code, Name, Market, Sector, MarketCap, Volume
    """
    market = config.get("market", "KRX")
    min_market_cap = config.get("screening_min_market_cap", 500_000_000_000)
    min_volume = config.get("screening_min_volume", 100_000)

    frames = []

    if market in ("KRX", "ALL"):
        logger.info("Building KRX universe...")
        try:
            krx_df = get_krx_universe(
                min_market_cap=min_market_cap,
                min_volume=min_volume,
            )
            if not krx_df.empty:
                krx_df["Market"] = "KRX"
                frames.append(krx_df)
                logger.info(f"KRX universe: {len(krx_df)} stocks")
        except Exception as e:
            logger.error(f"Failed to build KRX universe: {e}")

    if market in ("US", "ALL"):
        logger.info("Building US universe...")
        try:
            us_df = get_us_universe(
                universe_type=config.get("us_universe", "sp500"),
                custom_watchlist=config.get("custom_watchlist"),
            )
            if not us_df.empty:
                us_df["Market"] = "US"
                frames.append(us_df)
                logger.info(f"US universe: {len(us_df)} stocks")
        except Exception as e:
            logger.error(f"Failed to build US universe: {e}")

    if not frames:
        logger.warning("No stocks found in universe")
        return pd.DataFrame()

    universe = pd.concat(frames, ignore_index=True)
    logger.info(f"Total universe: {len(universe)} stocks")
    return universe
