# -*- coding: utf-8 -*-
"""
FinMind 基本面資料模組
用於獲取台灣股市基本面財務資料

API 文檔：https://finmind.github.io/tutor/TaiwanMarket/Fundamental/

可用的資料集：
- TaiwanStockFinancialStatements: 綜合損益表（1990-03-01 ~ now）
- TaiwanStockBalanceSheet: 資產負債表（2011-12-01 ~ now）
- TaiwanStockCashFlowsStatement: 現金流量表（2008-06-01 ~ now）
- TaiwanStockDividend: 股利政策表（2005-05-01 ~ now）
- TaiwanStockDividendResult: 除權除息結果表（2003-05-01 ~ now）
- TaiwanStockMonthRevenue: 月營收表（2002-02-01 ~ now）

注意：本模組僅使用公開可用的 API 端點，
不使用需要 backer/sponsor 會員資格的功能（如 TaiwanStockMarketValue）。
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np

from .finmind_common import (
    _make_api_request,
    format_date,
    get_default_start_date,
    normalize_stock_id,
    FinMindError,
    FinMindDataNotFoundError,
)


def _convert_to_serializable(obj):
    """
    將 numpy/pandas 資料類型轉換為 Python 原生類型，
    以便 JSON 序列化。
    """
    if isinstance(obj, dict):
        return {k: _convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_to_serializable(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    else:
        return obj


def _format_output(data: dict, use_toon: bool = True) -> str:
    """
    格式化輸出資料，支援 JSON 或 toon 格式。
    
    Args:
        data: 要輸出的資料字典
        use_toon: 是否使用 toon 格式。預設為 True（強制使用 toon）
        
    Returns:
        str: 格式化後的字串（JSON 或 toon 格式）
    """
    # 先確保資料可序列化
    serializable_data = _convert_to_serializable(data)
    
    if use_toon:
        try:
            from tradingagents.utils.toon_converter import convert_json_to_toon
            return convert_json_to_toon(serializable_data)
        except Exception as e:
            print(f"警告：toon 轉換失敗：{e}，使用 JSON 格式")
            return json.dumps(serializable_data, ensure_ascii=False, indent=2)
    else:
        return json.dumps(serializable_data, ensure_ascii=False, indent=2)


def get_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: Optional[str] = None,
    use_toon: bool = True
) -> str:
    """
    獲取綜合損益表（TaiwanStockFinancialStatements）。
    
    資料區間：1990-03-01 ~ now
    
    返回欄位：
    - date: 財報日期
    - stock_id: 股票代碼
    - type: 科目類型
    - value: 數值
    - origin_name: 原始科目名稱
    
    Args:
        ticker: 股票代碼（例如 "2330"）
        freq: 報告頻率（quarterly/annual）- 此參數保留但 FinMind 統一返回所有資料
        curr_date: 當前日期，用於計算查詢範圍
        use_toon: 是否使用 toon 格式（保留但未實作）
        
    Returns:
        str: JSON 格式的損益表資料
    """
    ticker = normalize_stock_id(ticker)
    
    # 計算日期範圍（往前推 3 年）
    if curr_date:
        end_date = format_date(curr_date)
        start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=3*365)
        start_date = format_date(start_dt)
    else:
        start_date = get_default_start_date(years_back=3)
        end_date = format_date(datetime.now())
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockFinancialStatements",
            data_id=ticker,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            df = pd.DataFrame(response["data"])
            
            # 只保留最近 2 期的資料以減少 token
            unique_dates = df["date"].unique()
            if len(unique_dates) > 2:
                recent_dates = sorted(unique_dates, reverse=True)[:2]
                df = df[df["date"].isin(recent_dates)]
            
            # 轉換為 pivot 格式（更易閱讀）
            try:
                pivot_df = df.pivot_table(
                    index="date",
                    columns="type",
                    values="value",
                    aggfunc="first"
                ).reset_index()
                
                result = {
                    "stock_id": ticker,
                    "report_type": "income_statement",
                    "data": pivot_df.to_dict(orient="records")
                }
            except Exception:
                # 如果 pivot 失敗，返回原始格式
                result = {
                    "stock_id": ticker,
                    "report_type": "income_statement",
                    "data": df.to_dict(orient="records")
                }
            
            return _format_output(result, use_toon)
        else:
            return _format_output({
                "stock_id": ticker,
                "report_type": "income_statement",
                "data": [],
                "message": "查無資料"
            }, use_toon)
            
    except FinMindDataNotFoundError:
        return _format_output({
            "stock_id": ticker,
            "report_type": "income_statement",
            "data": [],
            "message": f"找不到股票 {ticker} 的損益表資料"
        }, use_toon)
    except FinMindError as e:
        return _format_output({
            "error": str(e),
            "stock_id": ticker
        }, use_toon)


def get_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: Optional[str] = None,
    use_toon: bool = True
) -> str:
    """
    獲取資產負債表（TaiwanStockBalanceSheet）。
    
    資料區間：2011-12-01 ~ now
    
    返回欄位：
    - date: 財報日期
    - stock_id: 股票代碼
    - type: 科目類型
    - value: 數值
    - origin_name: 原始科目名稱
    
    Args:
        ticker: 股票代碼（例如 "2330"）
        freq: 報告頻率（quarterly/annual）
        curr_date: 當前日期
        use_toon: 是否使用 toon 格式
        
    Returns:
        str: JSON 格式的資產負債表資料
    """
    ticker = normalize_stock_id(ticker)
    
    if curr_date:
        end_date = format_date(curr_date)
        start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=3*365)
        start_date = format_date(start_dt)
    else:
        start_date = get_default_start_date(years_back=3)
        end_date = format_date(datetime.now())
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockBalanceSheet",
            data_id=ticker,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            df = pd.DataFrame(response["data"])
            
            # 只保留最近 2 期的資料
            unique_dates = df["date"].unique()
            if len(unique_dates) > 2:
                recent_dates = sorted(unique_dates, reverse=True)[:2]
                df = df[df["date"].isin(recent_dates)]
            
            # 轉換為 pivot 格式
            try:
                pivot_df = df.pivot_table(
                    index="date",
                    columns="type",
                    values="value",
                    aggfunc="first"
                ).reset_index()
                
                result = {
                    "stock_id": ticker,
                    "report_type": "balance_sheet",
                    "data": pivot_df.to_dict(orient="records")
                }
            except Exception:
                result = {
                    "stock_id": ticker,
                    "report_type": "balance_sheet",
                    "data": df.to_dict(orient="records")
                }
            
            return _format_output(result, use_toon)
        else:
            return _format_output({
                "stock_id": ticker,
                "report_type": "balance_sheet",
                "data": [],
                "message": "查無資料"
            }, use_toon)
            
    except FinMindDataNotFoundError:
        return _format_output({
            "stock_id": ticker,
            "report_type": "balance_sheet",
            "data": [],
            "message": f"找不到股票 {ticker} 的資產負債表資料"
        }, use_toon)
    except FinMindError as e:
        return _format_output({
            "error": str(e),
            "stock_id": ticker
        }, use_toon)


def get_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: Optional[str] = None,
    use_toon: bool = True
) -> str:
    """
    獲取現金流量表（TaiwanStockCashFlowsStatement）。
    
    資料區間：2008-06-01 ~ now
    
    Returns:
        str: JSON 格式的現金流量表資料
    """
    ticker = normalize_stock_id(ticker)
    
    if curr_date:
        end_date = format_date(curr_date)
        start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=3*365)
        start_date = format_date(start_dt)
    else:
        start_date = get_default_start_date(years_back=3)
        end_date = format_date(datetime.now())
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockCashFlowsStatement",
            data_id=ticker,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            df = pd.DataFrame(response["data"])
            
            unique_dates = df["date"].unique()
            if len(unique_dates) > 2:
                recent_dates = sorted(unique_dates, reverse=True)[:2]
                df = df[df["date"].isin(recent_dates)]
            
            try:
                pivot_df = df.pivot_table(
                    index="date",
                    columns="type",
                    values="value",
                    aggfunc="first"
                ).reset_index()
                
                result = {
                    "stock_id": ticker,
                    "report_type": "cashflow",
                    "data": pivot_df.to_dict(orient="records")
                }
            except Exception:
                result = {
                    "stock_id": ticker,
                    "report_type": "cashflow",
                    "data": df.to_dict(orient="records")
                }
            
            return _format_output(result, use_toon)
        else:
            return _format_output({
                "stock_id": ticker,
                "report_type": "cashflow",
                "data": [],
                "message": "查無資料"
            }, use_toon)
            
    except FinMindDataNotFoundError:
        return _format_output({
            "stock_id": ticker,
            "report_type": "cashflow",
            "data": [],
            "message": f"找不到股票 {ticker} 的現金流量表資料"
        }, use_toon)
    except FinMindError as e:
        return _format_output({
            "error": str(e),
            "stock_id": ticker
        }, use_toon)


def get_month_revenue(
    ticker: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    獲取月營收表（TaiwanStockMonthRevenue）。
    
    資料區間：2002-02-01 ~ now
    
    返回欄位：
    - date: 公布日期
    - stock_id: 股票代碼
    - country: 地區
    - revenue: 當月營收
    - revenue_month: 營收月份
    - revenue_year: 營收年份
    
    Returns:
        str: JSON 格式的月營收資料
    """
    ticker = normalize_stock_id(ticker)
    
    if not start_date:
        start_date = get_default_start_date(years_back=2)
    if not end_date:
        end_date = format_date(datetime.now())
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockMonthRevenue",
            data_id=ticker,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            df = pd.DataFrame(response["data"])
            
            # 只保留最近 12 個月的資料
            df = df.sort_values("date", ascending=False).head(12)
            
            result = {
                "stock_id": ticker,
                "report_type": "month_revenue",
                "data": df.to_dict(orient="records")
            }
            
            return _format_output(result)
        else:
            return _format_output({
                "stock_id": ticker,
                "report_type": "month_revenue",
                "data": [],
                "message": "查無資料"
            })
            
    except FinMindError as e:
        return _format_output({
            "error": str(e),
            "stock_id": ticker
        })


def get_dividend(
    ticker: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    獲取股利政策表（TaiwanStockDividend）。
    
    資料區間：2005-05-01 ~ now
    
    返回欄位包含現金股利、股票股利、除權息日等完整股利資訊。
    
    Returns:
        str: JSON 格式的股利政策資料
    """
    ticker = normalize_stock_id(ticker)
    
    if not start_date:
        start_date = get_default_start_date(years_back=5)
    if not end_date:
        end_date = format_date(datetime.now())
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockDividend",
            data_id=ticker,
            start_date=start_date,
            end_date=end_date
        )
        
        if "data" in response and response["data"]:
            df = pd.DataFrame(response["data"])
            
            # 只保留最近 10 筆
            df = df.sort_values("date", ascending=False).head(10)
            
            result = {
                "stock_id": ticker,
                "report_type": "dividend",
                "data": df.to_dict(orient="records")
            }
            
            return _format_output(result)
        else:
            return _format_output({
                "stock_id": ticker,
                "report_type": "dividend",
                "data": [],
                "message": "查無資料"
            })
            
    except FinMindError as e:
        return _format_output({
            "error": str(e),
            "stock_id": ticker
        })


def get_fundamentals(
    ticker: str,
    curr_date: Optional[str] = None,
    use_toon: bool = True
) -> str:
    """
    獲取公司綜合基本面資料。
    
    整合多個資料來源，提供完整的基本面概覽：
    - 最新月營收
    - 最近一期損益表摘要
    - 最近一期資產負債表摘要
    - 最近股利資訊
    
    Args:
        ticker: 股票代碼（例如 "2330"）
        curr_date: 當前日期 (YYYY-MM-DD)
        use_toon: 是否使用 toon 格式
        
    Returns:
        str: toon 格式的綜合基本面資料
    """
    ticker = normalize_stock_id(ticker)
    
    if not curr_date:
        curr_date = format_date(datetime.now())
    
    start_date = get_default_start_date(years_back=2)
    
    fundamentals = {
        "stock_id": ticker,
        "report_date": curr_date,
        "月營收": None,
        "損益表摘要": None,
        "資產負債表摘要": None,
        "股利政策": None,
    }
    
    # 1. 獲取月營收
    try:
        revenue_response = _make_api_request(
            dataset="TaiwanStockMonthRevenue",
            data_id=ticker,
            start_date=start_date,
            end_date=curr_date
        )
        
        if "data" in revenue_response and revenue_response["data"]:
            df = pd.DataFrame(revenue_response["data"])
            latest = df.sort_values("date", ascending=False).iloc[0]
            fundamentals["月營收"] = {
                "日期": latest.get("date"),
                "營收": latest.get("revenue"),
                "營收年份": latest.get("revenue_year"),
                "營收月份": latest.get("revenue_month"),
            }
    except FinMindError:
        pass
    
    # 2. 獲取損益表
    try:
        income_response = _make_api_request(
            dataset="TaiwanStockFinancialStatements",
            data_id=ticker,
            start_date=start_date,
            end_date=curr_date
        )
        
        if "data" in income_response and income_response["data"]:
            df = pd.DataFrame(income_response["data"])
            latest_date = df["date"].max()
            latest_data = df[df["date"] == latest_date]
            
            key_items = {}
            for _, row in latest_data.iterrows():
                key_items[row["type"]] = row["value"]
            
            fundamentals["損益表摘要"] = {
                "日期": latest_date,
                "關鍵指標": key_items
            }
    except FinMindError:
        pass
    
    # 3. 獲取資產負債表
    try:
        balance_response = _make_api_request(
            dataset="TaiwanStockBalanceSheet",
            data_id=ticker,
            start_date=start_date,
            end_date=curr_date
        )
        
        if "data" in balance_response and balance_response["data"]:
            df = pd.DataFrame(balance_response["data"])
            latest_date = df["date"].max()
            latest_data = df[df["date"] == latest_date]
            
            key_items = {}
            for _, row in latest_data.iterrows():
                key_items[row["type"]] = row["value"]
            
            fundamentals["資產負債表摘要"] = {
                "日期": latest_date,
                "關鍵指標": key_items
            }
    except FinMindError:
        pass
    
    # 4. 獲取股利資訊
    try:
        dividend_start = get_default_start_date(years_back=3)
        dividend_response = _make_api_request(
            dataset="TaiwanStockDividend",
            data_id=ticker,
            start_date=dividend_start,
            end_date=curr_date
        )
        
        if "data" in dividend_response and dividend_response["data"]:
            df = pd.DataFrame(dividend_response["data"])
            latest = df.sort_values("date", ascending=False).iloc[0].to_dict()
            
            # 只保留重要欄位
            key_fields = [
                "date", "year", 
                "CashEarningsDistribution", "StockEarningsDistribution",
                "CashExDividendTradingDate", "StockExDividendTradingDate"
            ]
            fundamentals["股利政策"] = {
                k: latest.get(k) for k in key_fields if k in latest
            }
    except FinMindError:
        pass
    
    # 轉換所有資料為可序列化的格式並輸出
    return _format_output(fundamentals, use_toon)


# 別名，與現有系統相容
get_financial_statements = get_income_statement
