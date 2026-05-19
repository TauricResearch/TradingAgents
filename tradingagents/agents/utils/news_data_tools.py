from langchain_core.tools import tool
from typing import Annotated, Optional
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve news data for a given ticker symbol.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing news data
    """
    return route_to_vendor("get_news", ticker, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[Optional[int], "Days to look back; omit to use the configured default"] = None,
    limit: Annotated[Optional[int], "Max articles to return; omit to use the configured default"] = None,
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
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
    Returns:
        str: A report of insider transaction data
    """
    return route_to_vendor("get_insider_transactions", ticker)


@tool
def get_company_announcements(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    category: Annotated[str, "Announcement category, e.g. 全部"] = "全部",
) -> str:
    """
    Retrieve company announcements for a given ticker symbol.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_company_announcements", ticker, start_date, end_date, category)


@tool
def get_company_event_signals(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve structured A-share company event signals derived from announcements.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_company_event_signals", ticker, start_date, end_date)


@tool
def get_market_activity(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve A-share market activity signals such as fund flow, northbound holdings,
    and margin-trading context.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_market_activity", ticker, curr_date)


@tool
def get_sector_rotation_context(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve A-share industry / concept board context for a ticker.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_sector_rotation_context", ticker, curr_date)


@tool
def get_sector_strength_snapshot(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    limit: Annotated[int, "Number of leading / lagging boards to summarize"] = 5,
) -> str:
    """
    Retrieve a ranked snapshot of leading and lagging A-share industry and
    concept boards.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_sector_strength_snapshot", curr_date, limit)


@tool
def get_relative_strength_context(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Lookback window for relative-strength comparison"] = 20,
) -> str:
    """
    Retrieve A-share relative-strength context versus benchmark and board
    rotation backdrop.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_relative_strength_context", ticker, curr_date, look_back_days)


@tool
def get_trading_constraint_context(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve A-share board-rule and special-treatment trading constraints for
    a ticker.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_trading_constraint_context", ticker, curr_date)


@tool
def get_limit_move_sentiment_context(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve A-share涨停/跌停 broad tape temperature context.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_limit_move_sentiment_context", curr_date)


@tool
def get_peer_comparison_context(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Lookback window for peer comparison"] = 20,
) -> str:
    """
    Retrieve A-share peer-comparison context against sampled industry and
    concept peers.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_peer_comparison_context", ticker, curr_date, look_back_days)


@tool
def get_corporate_action_pressure_context(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve A-share corporate-action pressure context derived from recent
    announcement events.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_corporate_action_pressure_context", ticker, start_date, end_date)


@tool
def get_unusual_trading_activity(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve A-share 龙虎榜 / unusual-trading activity context.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_unusual_trading_activity", ticker, start_date, end_date)


@tool
def get_capital_flow_regime_context(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    window: Annotated[int, "Number of recent observations to summarize"] = 10,
) -> str:
    """
    Retrieve medium-horizon A-share capital-flow regime context.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_capital_flow_regime_context", ticker, curr_date, window)


@tool
def get_decision_signal_summary(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve a consolidated A-share decision summary built from event and
    market-activity signals.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_decision_signal_summary", ticker, start_date, end_date, curr_date)


@tool
def get_xueqiu_sentiment(
    ticker: Annotated[str, "Ticker symbol"],
) -> str:
    """
    Retrieve Xueqiu retail sentiment / ranking signals for an A-share ticker.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_xueqiu_sentiment", ticker)


@tool
def get_caixin_news(
    ticker: Annotated[str, "Ticker symbol"],
    limit: Annotated[int, "Max articles to return"] = 10,
) -> str:
    """
    Retrieve ticker-related Caixin news snippets for A-share analysis.
    Uses the configured news_data vendor.
    """
    return route_to_vendor("get_caixin_news", ticker, limit)
