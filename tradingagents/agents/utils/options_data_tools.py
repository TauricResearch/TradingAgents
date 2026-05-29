from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_options_chain(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve an options-chain snapshot and derived signals for a ticker.

    Returns a Markdown report with: (1) Put/Call ratios (volume & OI, all
    expiries and near-expiry), (2) near-expiry ATM IV and put-call IV skew,
    (3) max pain plus the top open-interest call/put strikes, (4) unusual
    activity (contracts where today's volume exceeds open interest), and
    (5) day-over-day deltas vs the most recent cached snapshot.

    The underlying yfinance API only returns the LIVE chain; historical
    option chains are not available. Live snapshots are cached to parquet,
    so re-running this tool on subsequent days enables day-over-day signal
    comparison. For historical dates with no cached snapshot, an explicit
    notice is returned rather than a stale live chain.
    """
    return route_to_vendor("get_options_chain", ticker, curr_date)
