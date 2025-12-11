# -*- coding: utf-8 -*-
"""
FinMind 台灣股市資料整合模組

整合所有 FinMind API 功能的統一入口點。

API 文檔：
- 基本面：https://finmind.github.io/tutor/TaiwanMarket/Fundamental/
- 技術面：https://finmind.github.io/tutor/TaiwanMarket/Technical/
- 籌碼面：https://finmind.github.io/tutor/TaiwanMarket/Chip/

使用方式：
    from tradingagents.dataflows import finmind
    
    # 獲取股價
    stock_data = finmind.get_stock("2330", "2024-01-01", "2024-12-01")
    
    # 獲取基本面
    fundamentals = finmind.get_fundamentals("2330")
    
    # 獲取技術指標
    indicator = finmind.get_indicator("2330", "per", "2024-12-01", 30)

環境變數設定：
    export FINMIND_API_TOKEN='your_token_here'
    
    可在 https://finmindtrade.com/ 註冊獲取 Token
"""

# 從各子模組匯入函式
from .finmind_common import (
    # 例外類別
    FinMindError,
    FinMindRateLimitError,
    FinMindAuthenticationError,
    FinMindDataNotFoundError,
    # 工具函式
    get_api_token,
    format_date,
    get_default_start_date,
    normalize_stock_id,
    validate_taiwan_stock_id,
    # 市場類型判斷
    get_stock_market_type,
    get_yfinance_ticker,
    is_taiwan_stock,
    # 內部函式（供進階使用）
    _make_api_request,
    _filter_by_date_range,
    # 資料集定義
    FUNDAMENTAL_DATASETS,
    TECHNICAL_DATASETS,
    CHIP_DATASETS,
    RESTRICTED_DATASETS,
)

from .finmind_stock import (
    get_stock,
    get_stock_info,
    get_stock_per,
    get_day_trading,
)

from .finmind_fundamentals import (
    get_fundamentals,
    get_income_statement,
    get_balance_sheet,
    get_cashflow,
    get_month_revenue,
    get_dividend,
    get_financial_statements,
)

from .finmind_indicator import (
    get_indicator,
    get_margin_data,
    get_institutional_data,
    INDICATOR_DESCRIPTIONS,
)

from .finmind_news import (
    get_news,
    get_global_news,
    get_insider_sentiment,
    get_insider_transactions,
)


# 版本資訊
__version__ = "1.0.0"
__author__ = "TradingAgentsX"


# 便利函式：快速獲取股票完整資訊
def get_stock_overview(
    ticker: str,
    curr_date: str = None
) -> dict:
    """
    獲取股票的完整概覽，包含股價、基本面和籌碼面資訊。
    
    Args:
        ticker: 股票代碼（例如 "2330"）
        curr_date: 當前日期（預設為今天）
        
    Returns:
        dict: 包含各類資訊的字典
    """
    import json
    from datetime import datetime, timedelta
    
    if not curr_date:
        curr_date = datetime.now().strftime("%Y-%m-%d")
    
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    
    overview = {
        "ticker": ticker,
        "date": curr_date,
        "stock_price": None,
        "fundamentals": None,
        "per_pbr": None,
        "margin": None,
        "institutional": None,
    }
    
    try:
        # 股價
        stock_data = get_stock(ticker, start_date, curr_date)
        if stock_data and "error" not in stock_data.lower():
            overview["stock_price"] = "已獲取"
    except Exception:
        pass
    
    try:
        # 基本面
        fundamentals_data = get_fundamentals(ticker, curr_date)
        if fundamentals_data:
            overview["fundamentals"] = json.loads(fundamentals_data) if isinstance(fundamentals_data, str) else fundamentals_data
    except Exception:
        pass
    
    try:
        # PER/PBR
        per_data = get_stock_per(ticker, start_date, curr_date)
        if per_data and "error" not in per_data.lower():
            overview["per_pbr"] = "已獲取"
    except Exception:
        pass
    
    try:
        # 融資融券
        margin_data = get_margin_data(ticker, start_date, curr_date)
        if margin_data and "error" not in margin_data.lower():
            overview["margin"] = "已獲取"
    except Exception:
        pass
    
    try:
        # 法人買賣超
        inst_data = get_institutional_data(ticker, start_date, curr_date)
        if inst_data and "error" not in inst_data.lower():
            overview["institutional"] = "已獲取"
    except Exception:
        pass
    
    return overview


# 模組說明
__all__ = [
    # 例外類別
    "FinMindError",
    "FinMindRateLimitError",
    "FinMindAuthenticationError",
    "FinMindDataNotFoundError",
    
    # 股價相關
    "get_stock",
    "get_stock_info",
    "get_stock_per",
    "get_day_trading",
    
    # 基本面相關
    "get_fundamentals",
    "get_income_statement",
    "get_balance_sheet",
    "get_cashflow",
    "get_month_revenue",
    "get_dividend",
    "get_financial_statements",
    
    # 技術指標/籌碼面
    "get_indicator",
    "get_margin_data",
    "get_institutional_data",
    
    # 新聞相關
    "get_news",
    "get_global_news",
    "get_insider_sentiment",
    "get_insider_transactions",
    
    # 工具函式
    "get_stock_overview",
    "format_date",
    "get_default_start_date",
    "normalize_stock_id",
    "validate_taiwan_stock_id",
    # 市場類型判斷
    "get_stock_market_type",
    "get_yfinance_ticker",
    "is_taiwan_stock",
]
