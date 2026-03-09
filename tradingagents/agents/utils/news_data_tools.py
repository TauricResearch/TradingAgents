from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_news(
    ticker: Annotated[str, "股票代碼"],
    start_date: Annotated[str, "開始日期，格式為 yyyy-mm-dd"],
    end_date: Annotated[str, "結束日期，格式為 yyyy-mm-dd"],
) -> str:
    """
    檢索給定股票代碼的新聞數據。
    使用設定的新聞數據供應商。
    Args:
        ticker (str): 股票代碼
        start_date (str): 開始日期，格式為 yyyy-mm-dd
        end_date (str): 結束日期，格式為 yyyy-mm-dd
    Returns:
        str: 一個包含新聞數據的格式化字串
    """
    return route_to_vendor("get_news", ticker, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "當前日期，格式為 yyyy-mm-dd"],
    look_back_days: Annotated[int, "回溯天數"] = 7,
    limit: Annotated[int, "返回的最大文章數"] = 5,
) -> str:
    """
    檢索全球新聞數據。
    使用設定的新聞數據供應商。
    Args:
        curr_date (str): 當前日期，格式為 yyyy-mm-dd
        look_back_days (int): 回溯天數 (預設 7)
        limit (int): 返回的最大文章數 (預設 5)
    Returns:
        str: 一個包含全球新聞數據的格式化字串
    """
    look_back_days = int(look_back_days)
    limit = int(limit)
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_insider_sentiment(
    ticker: Annotated[str, "公司的股票代碼"],
    curr_date: Annotated[str, "您正在交易的當前日期，格式為 yyyy-mm-dd"],
) -> str:
    """
    檢索有關公司的內部人士情緒資訊。
    使用設定的新聞數據供應商。
    Args:
        ticker (str): 公司的股票代碼
        curr_date (str): 您正在交易的當前日期，格式為 yyyy-mm-dd
    Returns:
        str: 一份內部人士情緒數據的報告
    """
    return route_to_vendor("get_insider_sentiment", ticker, curr_date)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "股票代碼"],
    curr_date: Annotated[str, "您正在交易的當前日期，格式為 yyyy-mm-dd"],
) -> str:
    """
    檢索有關公司的內部人士交易資訊。
    使用設定的新聞數據供應商。
    Args:
        ticker (str): 公司的股票代碼
        curr_date (str): 您正在交易的當前日期，格式為 yyyy-mm-dd
    Returns:
        str: 一份內部人士交易數據的報告
    """
    return route_to_vendor("get_insider_transactions", ticker, curr_date)