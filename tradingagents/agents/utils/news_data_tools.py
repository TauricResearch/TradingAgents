from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_company_news(
    symbol: Annotated[str, "Exchange-qualified ticker symbol, such as AAPL or 005930.KS"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve company-specific news for a ticker symbol.
    Uses the configured news_data vendor chain.
    """
    return route_to_vendor("get_company_news", symbol, start_date, end_date)


@tool
def get_news(
    ticker: Annotated[str, "Exchange-qualified ticker symbol, such as AAPL or 005930.KS"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Backward-compatible thin wrapper for company news.
    This tool is equivalent to get_company_news(ticker, start_date, end_date).
    """
    return route_to_vendor("get_news", ticker, start_date, end_date)


@tool
def get_macro_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of calendar days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles or macro items to return"] = 10,
    region: Annotated[str | None, "Optional region hint such as US, KR, or GLOBAL"] = None,
    language: Annotated[str | None, "Optional language hint such as en or ko"] = None,
) -> str:
    """
    Retrieve macro and broader market context news.
    Uses the configured macro_data vendor chain.
    """
    return route_to_vendor(
        "get_macro_news",
        curr_date,
        look_back_days,
        limit,
        region=region,
        language=language,
    )


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of calendar days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles or macro items to return"] = 10,
) -> str:
    """
    Backward-compatible thin wrapper for macro news.
    This tool is equivalent to get_macro_news(curr_date, look_back_days, limit).
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)


@tool
def get_disclosures(
    symbol: Annotated[str, "Exchange-qualified ticker symbol, such as 005930.KS"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve company disclosures and filing events for a ticker symbol.
    Uses the configured disclosure_data vendor chain.
    """
    return route_to_vendor("get_disclosures", symbol, start_date, end_date)


@tool
def get_social_sentiment(
    symbol: Annotated[str, "Exchange-qualified ticker symbol, such as AAPL or 005930.KS"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve social or public-narrative sentiment for a ticker symbol.
    When a dedicated social vendor is unavailable, vendors may return a clearly labeled
    news-derived sentiment summary instead of claiming direct social-media coverage.
    """
    return route_to_vendor("get_social_sentiment", symbol, start_date, end_date)


@tool
def get_insider_transactions(
    ticker: Annotated[str, "Exchange-qualified ticker symbol"],
) -> str:
    """
    Retrieve insider transaction information for a company.
    Uses the configured fundamental_data vendor chain unless overridden at the tool level.
    """
    return route_to_vendor("get_insider_transactions", ticker)
