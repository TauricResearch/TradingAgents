# -*- coding: utf-8 -*-
"""
FinMind 股價資料模組
用於獲取台灣股市股價數據

API 文檔：https://finmind.github.io/tutor/TaiwanMarket/Technical/

可用的資料集：
- TaiwanStockPrice: 股價日成交資訊（1994-10-01 ~ now）
- TaiwanStockInfo: 台股總覽
- TaiwanStockPER: 個股 PER、PBR 資料

注意：本模組不使用需要 backer/sponsor 會員資格的功能
（如 TaiwanStockPriceAdj、TaiwanStockWeekPrice、TaiwanStockMonthPrice）
"""

import json
from datetime import datetime
from typing import Optional

from .finmind_common import (
    _make_api_request,
    format_date,
    normalize_stock_id,
    FinMindError,
    FinMindDataNotFoundError,
    _filter_by_date_range,
    format_output,
)


def get_stock(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """
    返回台灣股票的每日 OHLCV 數據。
    
    資料區間：1994-10-01 ~ now
    
    返回欄位：
    - date: 日期
    - stock_id: 股票代碼
    - Trading_Volume: 成交量
    - Trading_money: 成交金額
    - open: 開盤價
    - max: 最高價
    - min: 最低價
    - close: 收盤價
    - spread: 漲跌價差
    - Trading_turnover: 成交筆數
    
    Args:
        symbol: 股票代碼（例如 "2330"）
        start_date: 開始日期，格式為 YYYY-MM-DD
        end_date: 結束日期，格式為 YYYY-MM-DD
        
    Returns:
        str: CSV 格式的股價數據字串
    """
    symbol = normalize_stock_id(symbol)
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockPrice",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            data = response["data"]
            
            # 轉換為 CSV 格式（與 Alpha Vantage 保持一致）
            if not data:
                return "date,open,high,low,close,volume\n"
            
            # 建立 CSV 標頭
            csv_lines = ["date,open,high,low,close,volume"]
            
            for row in data:
                csv_lines.append(
                    f"{row.get('date', '')},"
                    f"{row.get('open', '')},"
                    f"{row.get('max', '')},"
                    f"{row.get('min', '')},"
                    f"{row.get('close', '')},"
                    f"{row.get('Trading_Volume', '')}"
                )
            
            return "\n".join(csv_lines)
        else:
            return "date,open,high,low,close,volume\n"
            
    except FinMindDataNotFoundError:
        return "date,open,high,low,close,volume\n"
    except FinMindError as e:
        print(f"警告：獲取股價數據失敗：{e}")
        return "date,open,high,low,close,volume\n"


def get_stock_info(stock_id: Optional[str] = None) -> str:
    """
    獲取台股總覽資訊。
    
    包含所有上市、上櫃、興櫃的股票名稱、代碼和產業類別。
    
    返回欄位：
    - industry_category: 產業類別
    - stock_id: 股票代碼
    - stock_name: 股票名稱
    - type: 類型（twse/tpex/rotc）
    - date: 更新日期
    
    Args:
        stock_id: 股票代碼（選填，可查詢特定股票）
        
    Returns:
        str: JSON 格式的股票資訊
    """
    try:
        response = _make_api_request(
            dataset="TaiwanStockInfo",
            data_id=stock_id
        )
        
        if "data" in response and response["data"]:
            # 如果查詢特定股票，只返回該股票的資訊
            if stock_id:
                stock_id = normalize_stock_id(stock_id)
                filtered = [
                    d for d in response["data"] 
                    if d.get("stock_id") == stock_id
                ]
                return format_output(filtered)
            else:
                # 限制返回數量以減少 token
                data = response["data"][:100]
                return format_output(data)
        else:
            return format_output([])
            
    except FinMindError as e:
        return format_output({"error": str(e)})


def get_stock_per(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """
    獲取個股 PER、PBR 資料。
    
    返回欄位：
    - date: 日期
    - stock_id: 股票代碼
    - dividend_yield: 殖利率
    - PER: 本益比
    - PBR: 股價淨值比
    
    Args:
        symbol: 股票代碼（例如 "2330"）
        start_date: 開始日期
        end_date: 結束日期
        
    Returns:
        str: JSON 格式的 PER/PBR 資料
    """
    symbol = normalize_stock_id(symbol)
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockPER",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            result = {
                "stock_id": symbol,
                "data": response["data"]
            }
            return format_output(result)
        else:
            return format_output({
                "stock_id": symbol,
                "data": [],
                "message": "查無資料"
            })
            
    except FinMindDataNotFoundError:
        return format_output({
            "stock_id": symbol,
            "data": [],
            "message": f"找不到股票 {symbol} 的 PER/PBR 資料"
        })
    except FinMindError as e:
        return format_output({
            "error": str(e),
            "stock_id": symbol
        })


def get_day_trading(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """
    獲取當日沖銷交易標的及成交量值。
    
    Args:
        symbol: 股票代碼（例如 "2330"）
        start_date: 開始日期
        end_date: 結束日期
        
    Returns:
        str: JSON 格式的當沖資料
    """
    symbol = normalize_stock_id(symbol)
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockDayTrading",
            data_id=symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            result = {
                "stock_id": symbol,
                "data": response["data"]
            }
            return format_output(result)
        else:
            return format_output({
                "stock_id": symbol,
                "data": [],
                "message": "查無資料"
            })
            
    except FinMindError as e:
        return format_output({
            "error": str(e),
            "stock_id": symbol
        })
