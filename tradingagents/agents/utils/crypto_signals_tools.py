from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_crypto_funding_rate(
    ticker: Annotated[str, "Crypto ticker, e.g. 'BTC-USD'"],
) -> str:
    """
    Retrieve the recent perpetual futures funding rate history for a crypto
    ticker. Funding is paid between longs and shorts every 8 hours to keep
    the perpetual price anchored to spot; persistently positive rates mean
    longs are paying shorts (crowded/expensive long positioning, a
    contrarian caution signal), persistently negative rates mean the
    opposite (crowded shorts, potential short-squeeze fuel). Uses the
    configured crypto_signals vendor.

    Args:
        ticker (str): Crypto ticker, e.g. "BTC-USD"

    Returns:
        str: A formatted markdown report of the last few funding rate prints.
    """
    return route_to_vendor("get_crypto_funding_rate", ticker)


@tool
def get_crypto_open_interest(
    ticker: Annotated[str, "Crypto ticker, e.g. 'BTC-USD'"],
) -> str:
    """
    Retrieve current perpetual futures open interest for a crypto ticker.
    Rising open interest alongside a rising price usually confirms a trend
    (new money entering); rising OI with a falling price often signals
    aggressive new shorts; falling OI signals position unwinding /
    deleveraging. Uses the configured crypto_signals vendor.

    Args:
        ticker (str): Crypto ticker, e.g. "BTC-USD"

    Returns:
        str: A formatted markdown report with current open interest.
    """
    return route_to_vendor("get_crypto_open_interest", ticker)


@tool
def get_crypto_fear_greed_index() -> str:
    """
    Retrieve the market-wide Crypto Fear & Greed Index, a composite of
    volatility, momentum, social volume, dominance, and search trends.
    0-24 = Extreme Fear (often a contrarian buy zone), 25-49 = Fear,
    50-74 = Greed, 75-100 = Extreme Greed (often a contrarian caution zone).
    This is a whole-market gauge, not ticker-specific. Uses the configured
    crypto_signals vendor.

    Returns:
        str: A formatted markdown report of the last few daily readings.
    """
    return route_to_vendor("get_crypto_fear_greed_index")


@tool
def get_bitcoin_network_hashrate() -> str:
    """
    Retrieve Bitcoin network hashrate and difficulty. A rising hashrate
    signals miner confidence/network security strength; a sharp drop can
    precede or accompany capitulation-driven sell pressure from miners.
    Bitcoin-specific — not meaningful for other assets. Uses the configured
    crypto_signals vendor.

    Returns:
        str: A formatted markdown report with current hashrate/difficulty
        and a short recent trend.
    """
    return route_to_vendor("get_bitcoin_network_hashrate")
