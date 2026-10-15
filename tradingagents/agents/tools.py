"""The data tools the analysts call.

Each dated tool takes the run's ``trade_date`` from graph state (``InjectedState``)
and never serves data past it, whatever date the model asks for.
"""

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import as_of, as_of_window
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.reconciliation import build_reconciliation_note
from tradingagents.dataflows.router import (
    VENDOR_METHODS,
    get_vendor,
    no_data_available,
    route_to_vendor,
    vendor_unavailable,
)
from tradingagents.dataflows.vendors.yahoo.snapshot import build_verified_market_snapshot

# Sentinels the routing layer returns when no vendor served data; there is
# nothing to reconcile against, so skip the cross-vendor note.
_NO_DATA_SENTINELS = ("NO_DATA_AVAILABLE", "DATA_UNAVAILABLE")


def _vendor_chain(method: str, vendor_config: str) -> list[str]:
    """The configured vendor chain for a method, resolved like the router.

    ``default`` expands to every available vendor; an explicit list keeps only
    the configured vendors that actually implement the method.
    """
    available = VENDOR_METHODS.get(method, {})
    chain = [v.strip() for v in vendor_config.split(",")]
    explicit = [v for v in chain if v and v != "default"]
    if explicit:
        return [v for v in explicit if v in available]
    return list(available.keys())


def _cross_vendor_note(symbol: str, start_date: str, end_date: str, primary_csv: str) -> str | None:
    """A best-effort cross-vendor divergence note for the primary OHLCV result.

    Only runs when a *less-trusted* source served the primary data (Alpha
    Vantage, detected by its ``# Alpha Vantage`` header). In that case it
    compares the primary's closes against the other configured OHLCV vendor
    (normally yfinance — free and high-coverage) and appends a human-readable
    note when they diverge meaningfully. When yfinance is the primary, the data
    is not in question and no second vendor call is made, so the healthy path
    adds zero latency and no extra rate-limit cost.

    Deliberately non-invasive: it never raises, never mutates or replaces the
    primary result, and yields ``None`` (nothing appended) when the feature is
    disabled, the primary has no data, the primary is the trusted source,
    there is no second source, or no second source diverges. Ticker-agnostic —
    it only reads the date and close columns every OHLCV vendor emits.
    """
    if not get_config().get("cross_vendor_reconciliation", True):
        return None
    if not primary_csv or primary_csv.startswith(_NO_DATA_SENTINELS):
        return None
    if not primary_csv.startswith("# Alpha Vantage"):
        return None  # yfinance (or the trusted primary) served — nothing to verify

    method = "get_stock_data"
    chain = _vendor_chain(method, get_vendor("core_stock_apis", method))
    # The primary came from alpha_vantage; verify it against the other source.
    for vendor in chain:
        if vendor == "alpha_vantage":
            continue  # the primary itself
        impl = VENDOR_METHODS.get(method, {}).get(vendor)
        if impl is None:
            continue
        try:
            comparison = impl(symbol, start_date, end_date)
        except Exception:
            continue  # a comparison source that errors is not the primary's job to fix
        if not comparison or comparison.startswith(_NO_DATA_SENTINELS):
            continue
        try:
            return build_reconciliation_note(symbol, primary_csv, comparison)
        except Exception:
            return None
    return None


@tool
def get_stock_data(
    symbol: Annotated[str, InjectedState("company_of_interest")],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve stock price data (OHLCV) for the instrument under analysis.
    Uses the configured core_stock_apis vendor.
    Args:
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted dataframe containing the price data for the instrument over the date range.
    """
    try:
        start_date, end_date = as_of_window(start_date, end_date, trade_date)
    except ValueError as e:
        return str(e)
    primary = route_to_vendor("get_stock_data", symbol, start_date, end_date)
    note = _cross_vendor_note(symbol, start_date, end_date, primary)
    if note:
        primary += f"\n{note}"
    return primary


@tool
def get_indicators(
    symbol: Annotated[str, InjectedState("company_of_interest")],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve a single technical indicator for the instrument under analysis.
    Uses the configured technical_indicators vendor.
    Args:
        indicator (str): A single technical indicator name, e.g. 'rsi', 'macd'. Call this tool once per indicator.
        curr_date (str): The current trading date you are trading on, YYYY-mm-dd
        look_back_days (int): How many days to look back, default is 30
    Returns:
        str: A formatted dataframe containing the technical indicators for the instrument and indicator.
    """
    # LLMs sometimes pass multiple indicators as a comma-separated string;
    # split and process each individually.
    curr_date = as_of(curr_date, trade_date)
    indicators = [i.strip().lower() for i in indicator.split(",") if i.strip()]
    results = []
    for ind in indicators:
        try:
            results.append(route_to_vendor("get_indicators", symbol, ind, curr_date, look_back_days))
        except ValueError as e:
            results.append(str(e))
    return "\n\n".join(results)


@tool
def get_verified_market_snapshot(
    symbol: Annotated[str, InjectedState("company_of_interest")],
    curr_date: Annotated[str, "the current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[
        int, "number of recent trading rows to include for sanity-checking"
    ] = 30,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """Deterministic verification snapshot for exact market-data claims.

    Returns the latest OHLCV row on or before curr_date, common technical
    indicators, and recent closes. Call this before making exact claims about
    price levels, Bollinger bands, RSI, MACD, moving averages, support /
    resistance, or historical comparisons, and treat it as the source of truth.
    """
    # An exception out of a tool would end the run.
    try:
        return build_verified_market_snapshot(symbol, as_of(curr_date, trade_date), look_back_days)
    except VendorUnavailableError as exc:
        return vendor_unavailable("get_verified_market_snapshot", exc)
    except NoMarketDataError as exc:
        return no_data_available(exc)


@tool
def get_fundamentals(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve comprehensive fundamental data for the instrument under analysis.
    Uses the configured fundamental_data vendor.
    Args:
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing comprehensive fundamental data
    """
    return route_to_vendor("get_fundamentals", ticker, as_of(curr_date, trade_date))


@tool
def get_balance_sheet(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve balance sheet data for the instrument under analysis.
    Uses the configured fundamental_data vendor.
    Args:
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing balance sheet data
    """
    return route_to_vendor("get_balance_sheet", ticker, freq, as_of(curr_date, trade_date))


@tool
def get_cashflow(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve cash flow statement data for the instrument under analysis.
    Uses the configured fundamental_data vendor.
    Args:
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing cash flow statement data
    """
    return route_to_vendor("get_cashflow", ticker, freq, as_of(curr_date, trade_date))


@tool
def get_income_statement(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve income statement data for the instrument under analysis.
    Uses the configured fundamental_data vendor.
    Args:
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing income statement data
    """
    return route_to_vendor("get_income_statement", ticker, freq, as_of(curr_date, trade_date))


@tool
def get_news(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve news data for the instrument under analysis.
    Uses the configured news_data vendor.
    Args:
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing news data
    """
    try:
        start_date, end_date = as_of_window(start_date, end_date, trade_date)
    except ValueError as e:
        return str(e)
    return route_to_vendor("get_news", ticker, start_date, end_date)


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int | None, "Days to look back; omit to use the configured default"] = None,
    limit: Annotated[int | None, "Max articles to return; omit to use the configured default"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor. Defaults for look_back_days and
    limit come from DEFAULT_CONFIG (global_news_lookback_days,
    global_news_article_limit); pass explicit values to override.

    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back; omit to inherit config
        limit (int): Maximum number of articles to return; omit to inherit config

    Returns:
        str: A formatted string containing global news data
    """
    return route_to_vendor("get_global_news", as_of(curr_date, trade_date), look_back_days, limit)


@tool
def get_insider_transactions(
    ticker: Annotated[str, InjectedState("company_of_interest")],
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Returns:
        str: A report of insider transaction data
    """
    return route_to_vendor("get_insider_transactions", ticker, trade_date or None)


@tool
def get_macro_indicators(
    indicator: Annotated[
        str,
        "Macro indicator: a friendly alias such as 'cpi', 'core_pce', "
        "'unemployment', 'fed_funds_rate', '10y_treasury', 'yield_curve', "
        "'real_gdp', 'vix', euro-area aliases such as 'ecb_deposit_rate', "
        "'euro_hicp', 'euro_core_hicp', 'euro_real_gdp', 'germany_10y', "
        "'france_10y', 'eur_usd', or a raw FRED series ID such as 'CPIAUCSL'.",
    ],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format; the end of the window"],
    look_back_days: Annotated[
        int | None, "Trailing window length in days; omit for a 1-year window"
    ] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve a macroeconomic indicator time series. ECB and Eurostat official
    APIs cover selected German/euro-area series (e.g. ``germany_hicp``,
    ``germany_real_gdp``, ``euro_hicp``, ``ecb_deposit_rate``); unsupported names
    continue to FRED when configured. Returns source, unit, observation window,
    and recent values. Historical Eurostat values use the current source vintage.
    Uses the configured macro_data vendor chain.

    Args:
        indicator (str): Friendly alias or raw FRED series ID
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Trailing window length; omit for a 1-year window

    Returns:
        str: A formatted markdown report of the macro series
    """
    return route_to_vendor("get_macro_indicators", indicator, as_of(curr_date, trade_date), look_back_days)


@tool
def get_prediction_markets(
    topic: Annotated[
        str,
        "Event topic/keyword, e.g. 'Fed rate cut', 'recession 2026', "
        "'US election', or a sector/company event.",
    ],
    limit: Annotated[int | None, "Max markets to return; omit for a default of 6"] = None,
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """
    Retrieve live, market-implied probabilities for forward-looking events from
    prediction markets (Polymarket): Fed decisions, recession, elections,
    geopolitics, crypto. Returns the most-traded open markets matching the
    topic, each with its implied probability, traded volume, resolution date,
    and recent move. Uses the configured prediction_markets vendor.

    Args:
        topic (str): Event keyword(s) to search
        limit (int): Max markets to return; omit for a default of 6

    Returns:
        str: A formatted markdown report of matching prediction markets
    """
    return route_to_vendor("get_prediction_markets", topic, limit, trade_date or None)
