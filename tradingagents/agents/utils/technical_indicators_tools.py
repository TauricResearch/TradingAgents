from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_indicators(
    symbol: Annotated[str, "公司的股票代碼"],
    indicator: Annotated[str, """技術指標名稱。
    常用指標：MA (移動平均), RSI, MACD。
    使用簡寫名稱如：'MA', 'RSI', 'MACD'，
    或指定期間如：'close_50_sma', 'close_200_sma'。
    範例：'MA' 或 'RSI' 或 'MACD'"""],
    curr_date: Annotated[str, "您正在交易的當前交易日期，格式為 YYYY-mm-dd"],
    look_back_days: Annotated[int, "回溯天數"] = 30,
) -> str:
    """
    檢索給定股票代碼的技術指標。
    使用設定的技術指標供應商。
    
    支持的指標：
    - MA/SMA: 簡單移動平均線（使用 look_back_days 或指定 'close_50_sma', 'close_200_sma'）
    - EMA: 指數移動平均線
    - RSI: 相對強弱指數
    - MACD: 移動平均收斂背離
    - BOLL: 布林通道
    - ATR: 平均真實波幅
    - VWMA: 成交量加權移動平均
    - MFI: 資金流量指數
    
    Args:
        symbol (str): 公司的股票代碼，例如 AAPL, TSM
        indicator (str): 技術指標名稱，使用簡寫（MA, RSI, MACD 等）
        curr_date (str): 您正在交易的當前交易日期，格式為 YYYY-mm-dd
        look_back_days (int): 回溯天數，預設為 30
    Returns:
        str: 一個格式化的數據框，包含指定股票代碼和指標的技術指標。
    """
    look_back_days = int(look_back_days)
    # 規範化指標名稱以匹配供應商的預期格式
    indicator_lower = indicator.lower().strip()
    
    # 處理常見的變體 - 包含 "moving average" 的完整詞
    if "50" in indicator_lower and ("ma" in indicator_lower or "avg" in indicator_lower or "moving" in indicator_lower):
        normalized_indicator = "close_50_sma"
    elif "200" in indicator_lower and ("ma" in indicator_lower or "avg" in indicator_lower or "moving" in indicator_lower):
        normalized_indicator = "close_200_sma"
    elif "10" in indicator_lower and "ema" in indicator_lower:
        normalized_indicator = "close_10_ema"
    # 處理通用指標名稱，使用 look_back_days
    elif indicator_lower in ["sma", "ma", "moving average", "simple moving average"]:
        normalized_indicator = f"close_{look_back_days}_sma"
    elif indicator_lower in ["ema", "exponential moving average"]:
        normalized_indicator = f"close_{look_back_days}_ema"
    else:
        # 常見指標名稱映射 - 擴充版
        mapping = {
            # SMA 變體
            "sma50": "close_50_sma",
            "sma200": "close_200_sma",
            "50-day ma": "close_50_sma",
            "200-day ma": "close_200_sma",
            "50 day ma": "close_50_sma",
            "200 day ma": "close_200_sma",
            "50-day moving average": "close_50_sma",
            "200-day moving average": "close_200_sma",
            "50 day moving average": "close_50_sma",
            "200 day moving average": "close_200_sma",
            "50-day simple moving average": "close_50_sma",
            "200-day simple moving average": "close_200_sma",
            
            # EMA 變體
            "ema10": "close_10_ema",
            "10-day ema": "close_10_ema",
            "10 day ema": "close_10_ema",
            
            # Bollinger Bands
            "bbands": "boll",
            "bollinger": "boll",
            "bollinger bands": "boll",
            "bb": "boll",
            
            # MACD 變體
            "macd_signal": "macds",
            "macd signal": "macds",
            "macd_hist": "macdh",
            "macd histogram": "macdh",
            
            # 其他常見別名
            "relative strength index": "rsi",
            "average true range": "atr",
            "money flow index": "mfi",
        }
        
        # 如果在映射中，使用映射名稱
        if indicator_lower in mapping:
            normalized_indicator = mapping[indicator_lower]
        # 如果已經是正確的格式（例如 rsi, macd, atr），則保持原樣（轉小寫）
        else:
            normalized_indicator = indicator_lower
        
    return route_to_vendor("get_indicators", symbol, normalized_indicator, curr_date, look_back_days)
