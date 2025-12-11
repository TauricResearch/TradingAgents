# -*- coding: utf-8 -*-
"""
FinMind API 共用工具模組
用於與 FinMind 台灣股市資料 API 進行互動

API 文檔：https://finmind.github.io/

注意：本模組僅使用公開可用的 API 端點，
不使用需要 backer/sponsor 會員資格的功能。
"""

import os
import requests
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
from io import StringIO

# ============================================================================
# 常數定義
# ============================================================================

API_BASE_URL = "https://api.finmindtrade.com/api/v4/data"

# 可用的公開資料集（不需要 backer/sponsor 會員）
# 基本面
FUNDAMENTAL_DATASETS = {
    "financial_statements": "TaiwanStockFinancialStatements",  # 綜合損益表
    "balance_sheet": "TaiwanStockBalanceSheet",                # 資產負債表
    "cashflow": "TaiwanStockCashFlowsStatement",               # 現金流量表
    "dividend": "TaiwanStockDividend",                         # 股利政策表
    "dividend_result": "TaiwanStockDividendResult",            # 除權除息結果表
    "month_revenue": "TaiwanStockMonthRevenue",                # 月營收表
    "capital_reduction": "TaiwanStockCapitalReductionReferencePrice",  # 減資恢復買賣參考價格
    "delisting": "TaiwanStockDelisting",                       # 台灣股票下市櫃表
    "split_price": "TaiwanStockSplitPrice",                    # 台股分割後參考價
    "par_value_change": "TaiwanStockParValueChange",           # 變更面額恢復買賣參考價格
}

# 技術面
TECHNICAL_DATASETS = {
    "stock_info": "TaiwanStockInfo",                           # 台股總覽
    "stock_info_warrant": "TaiwanStockInfoWithWarrant",        # 台股總覽（含權證）
    "trading_date": "TaiwanStockTradingDate",                  # 台股交易日
    "stock_price": "TaiwanStockPrice",                         # 股價日成交資訊
    "stock_per": "TaiwanStockPER",                             # PER、PBR 資料
    "order_book_trade": "TaiwanStockStatisticsOfOrderBookAndTrade",  # 每5秒委託成交統計
    "indicators_5sec": "TaiwanVariousIndicators5Seconds",      # 台股加權指數
    "day_trading": "TaiwanStockDayTrading",                    # 當日沖銷交易
    "total_return_index": "TaiwanStockTotalReturnIndex",       # 加權、櫃買報酬指數
}

# 籌碼面
CHIP_DATASETS = {
    "margin_purchase": "TaiwanStockMarginPurchaseShortSale",   # 個股融資融劵表
    "margin_total": "TaiwanStockTotalMarginPurchaseShortSale", # 整體市場融資融劵表
    "institutional": "TaiwanStockInstitutionalInvestorsBuySell",  # 法人買賣表
    "institutional_total": "TaiwanStockTotalInstitutionalInvestors",  # 市場三大法人買賣表
    "shareholding": "TaiwanStockShareholding",                 # 外資持股表
    "securities_lending": "TaiwanStockSecuritiesLending",      # 借券成交明細
    "short_sale_suspension": "TaiwanStockMarginShortSaleSuspension",  # 暫停融券賣出表
    "short_sale_balances": "TaiwanDailyShortSaleBalances",     # 信用額度總量管制餘額表
    "securities_trader_info": "TaiwanSecuritiesTraderInfo",    # 證券商資訊表
}

# 需要 backer/sponsor 會員的資料集（不使用）
RESTRICTED_DATASETS = [
    "TaiwanStockMarketValue",               # 台灣股價市值表
    "TaiwanStockMarketValueWeight",         # 台股市值比重表
    "TaiwanStockWeekPrice",                 # 台股週 K 資料表
    "TaiwanStockMonthPrice",                # 台股月 K 資料表
    "TaiwanStockPriceAdj",                  # 台灣還原股價資料表
    "TaiwanStockPriceTick",                 # 台灣股價歷史逐筆資料表
    "TaiwanStock10Year",                    # 台灣個股十年線資料表
    "TaiwanStockKBar",                      # 台股分 K 資料表
    "TaiwanStockEvery5SecondsIndex",        # 每 5 秒指數統計
    "TaiwanStockHoldingSharesPer",          # 股權持股分級表
    "TaiwanStockTradingDailyReport",        # 台股分點資料表
    "TaiwanStockWarrantTradingDailyReport", # 台股權證分點資料表
    "TaiwanstockGovernmentBankBuySell",     # 台股八大行庫賣賣表
    "TaiwanTotalExchangeMarginMaintenance", # 台灣大盤融資維持率
    "TaiwanStockTradingDailyReportSecIdAgg",# 當日卷商分點統計表
    "TaiwanStockDispositionSecuritiesPeriod",# 公布處置有價證券表
    "TaiwanStockInfoWithWarrantSummary",    # 台股權證標的對照表
]


# ============================================================================
# 自定義例外
# ============================================================================

class FinMindError(Exception):
    """FinMind API 通用錯誤"""
    pass


class FinMindRateLimitError(FinMindError):
    """當超過 FinMind API 速率限制時引發的例外"""
    pass


class FinMindAuthenticationError(FinMindError):
    """當 API Token 無效或缺失時引發的例外"""
    pass


class FinMindDataNotFoundError(FinMindError):
    """當查詢的資料不存在時引發的例外"""
    pass


# ============================================================================
# API Token 管理
# ============================================================================

def get_api_token() -> str:
    """
    從環境變數中檢索 FinMind 的 API Token。
    
    FinMind 使用 Bearer Token 進行身份驗證。
    您可以在 https://finmindtrade.com/ 註冊後獲取 Token。
    
    Returns:
        str: API Token
        
    Raises:
        FinMindAuthenticationError: 當環境變數未設定時
    """
    token = os.getenv("FINMIND_API_TOKEN")
    if not token:
        # 也支援舊的環境變數名稱
        token = os.getenv("FINMIND_API_KEY")
    
    if not token:
        raise FinMindAuthenticationError(
            "未設定 FINMIND_API_TOKEN 環境變數。"
            "請在 https://finmindtrade.com/ 註冊並獲取 Token，"
            "然後設定環境變數：export FINMIND_API_TOKEN='your_token'"
        )
    return token


# ============================================================================
# 日期格式處理
# ============================================================================

def format_date(date_input: Union[str, datetime]) -> str:
    """
    將各種日期格式轉換為 FinMind API 所需的 YYYY-MM-DD 格式。
    
    Args:
        date_input: 日期字串或 datetime 物件
        
    Returns:
        str: 格式化後的日期字串 (YYYY-MM-DD)
        
    Raises:
        ValueError: 當日期格式不支援時
    """
    if isinstance(date_input, datetime):
        return date_input.strftime("%Y-%m-%d")
    
    if isinstance(date_input, str):
        # 如果已經是正確格式，直接返回
        if len(date_input) == 10 and date_input[4] == '-' and date_input[7] == '-':
            return date_input
        
        # 嘗試解析常見的日期格式
        formats_to_try = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y%m%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]
        
        for fmt in formats_to_try:
            try:
                dt = datetime.strptime(date_input, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        raise ValueError(f"不支援的日期格式：{date_input}")
    
    raise ValueError(f"日期必須是字串或 datetime 物件，但得到的是 {type(date_input)}")


def get_default_start_date(years_back: int = 3) -> str:
    """
    獲取預設的開始日期（預設為往前推算指定年數）。
    
    Args:
        years_back: 往前推算的年數
        
    Returns:
        str: 格式化的開始日期
    """
    start_date = datetime.now() - timedelta(days=years_back * 365)
    return format_date(start_date)


# ============================================================================
# 輸出格式化（toon / JSON）
# ============================================================================

def _convert_to_serializable(obj):
    """
    將 numpy/pandas 資料類型轉換為 Python 原生類型，
    以便 JSON 序列化。
    """
    import numpy as np
    import pandas as pd
    
    if isinstance(obj, dict):
        return {k: _convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_to_serializable(item) for item in obj]
    elif hasattr(obj, 'item'):  # numpy scalar types
        return obj.item()
    elif hasattr(obj, 'tolist'):  # numpy array
        return obj.tolist()
    elif pd.isna(obj):
        return None
    else:
        return obj


def format_output(data: dict, use_toon: bool = True) -> str:
    """
    格式化輸出資料，強制使用 toon 格式以減少 token 消耗。
    
    toon 格式可以大幅減少 token 消耗（通常節省 40-60%）。
    
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


# ============================================================================
# API 請求處理
# ============================================================================

def _make_api_request(
    dataset: str,
    data_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    **extra_params
) -> Dict[str, Any]:
    """
    發送 API 請求並處理回應的輔助函式。
    
    根據 FinMind 文檔，API 請求格式為：
    GET https://api.finmindtrade.com/api/v4/data
    
    必要參數：
    - dataset: 資料集名稱
    
    選填參數：
    - data_id: 股票代碼（例如 "2330"）
    - start_date: 開始日期
    - end_date: 結束日期
    
    Args:
        dataset: FinMind 資料集名稱
        data_id: 股票代碼（例如 "2330"）
        start_date: 開始日期 (YYYY-MM-DD)
        end_date: 結束日期 (YYYY-MM-DD)
        **extra_params: 額外的查詢參數
        
    Returns:
        dict: API 回應的 JSON 資料
        
    Raises:
        FinMindRateLimitError: 當超過 API 速率限制時
        FinMindAuthenticationError: 當 Token 無效時
        FinMindDataNotFoundError: 當資料不存在時
        FinMindError: 其他 API 錯誤
    """
    # 獲取 Token
    token = get_api_token()
    
    # 建立請求標頭
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    # 建立請求參數
    params = {
        "dataset": dataset,
    }
    
    # 添加股票代碼（如果提供）
    if data_id:
        params["data_id"] = normalize_stock_id(data_id)
    
    # 添加開始日期（如果提供）
    if start_date:
        params["start_date"] = format_date(start_date)
    
    # 添加結束日期（如果提供）
    if end_date:
        params["end_date"] = format_date(end_date)
    
    # 添加額外參數
    params.update(extra_params)
    
    try:
        response = requests.get(
            API_BASE_URL,
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        
        # 解析 JSON 回應
        data = response.json()
        
        # 檢查 API 層級的錯誤
        if "msg" in data:
            msg = data["msg"].lower()
            
            # 速率限制錯誤
            if "rate limit" in msg or "too many requests" in msg:
                raise FinMindRateLimitError(f"超過 FinMind API 速率限制：{data['msg']}")
            
            # 認證錯誤
            if "token" in msg or "authentication" in msg or "unauthorized" in msg:
                raise FinMindAuthenticationError(f"FinMind API 認證失敗：{data['msg']}")
            
            # 資料不存在
            if "no data" in msg or "not found" in msg:
                raise FinMindDataNotFoundError(f"查無資料：{data['msg']}")
            
            # 其他錯誤
            if data.get("status") != 200:
                raise FinMindError(f"FinMind API 錯誤：{data['msg']}")
        
        return data
        
    except requests.exceptions.Timeout:
        raise FinMindError("FinMind API 請求超時")
    except requests.exceptions.RequestException as e:
        raise FinMindError(f"FinMind API 請求失敗：{str(e)}")
    except json.JSONDecodeError:
        raise FinMindError("無法解析 FinMind API 回應")


# ============================================================================
# 資料驗證和處理工具
# ============================================================================

def validate_taiwan_stock_id(stock_id: str) -> bool:
    """
    驗證台灣股票代碼格式。
    
    台灣股票代碼通常為 4-6 位數字，
    ETF 或特殊商品可能包含字母。
    
    Args:
        stock_id: 股票代碼
        
    Returns:
        bool: 是否為有效的股票代碼格式
    """
    if not stock_id:
        return False
    
    # 移除空白
    stock_id = stock_id.strip()
    
    # 基本長度檢查
    if len(stock_id) < 4 or len(stock_id) > 6:
        return False
    
    # 大多數台股代碼為純數字
    if stock_id.isdigit():
        return True
    
    # 某些 ETF 或特殊商品可能包含字母（如 00878）
    if stock_id[0].isdigit():
        return True
    
    return False


def normalize_stock_id(stock_id: str) -> str:
    """
    標準化股票代碼格式。
    
    Args:
        stock_id: 股票代碼
        
    Returns:
        str: 標準化後的股票代碼
    """
    # 移除空白和特殊字元
    normalized = stock_id.strip().upper()
    
    # 移除可能的 .TW 或 .TWO 後綴（台股在某些系統的格式）
    for suffix in [".TW", ".TWO", ".TT"]:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break
    
    return normalized


def _filter_by_date_range(
    data: list,
    date_field: str,
    start_date: str,
    end_date: str
) -> list:
    """
    按日期範圍過濾資料列表。
    
    Args:
        data: 要過濾的資料列表
        date_field: 日期欄位名稱
        start_date: 開始日期
        end_date: 結束日期
        
    Returns:
        list: 過濾後的資料列表
    """
    if not data:
        return data
    
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        filtered = []
        for item in data:
            if date_field in item:
                try:
                    item_date = datetime.strptime(item[date_field], "%Y-%m-%d")
                    if start_dt <= item_date <= end_dt:
                        filtered.append(item)
                except (ValueError, TypeError):
                    continue
        
        return filtered
    except Exception:
        return data


# ============================================================================
# 台股市場類型判斷
# ============================================================================

# 股票市場類型緩存（避免重複查詢）
_stock_market_type_cache: Dict[str, str] = {}


def get_stock_market_type(stock_id: str) -> str:
    """
    獲取台股的市場類型（上市/上櫃/興櫃）。
    
    透過 FinMind 的 TaiwanStockInfo API 查詢股票資訊，
    根據 type 欄位判斷市場類型：
    - twse: 上市（Yahoo Finance 後綴 .TW）
    - tpex: 上櫃（Yahoo Finance 後綴 .TWO）
    - rotc: 興櫃（Yahoo Finance 後綴 .TWO）
    
    Args:
        stock_id: 台灣股票代碼（例如 "2330"）
        
    Returns:
        str: 市場類型代碼 ("twse", "tpex", "rotc") 或 "unknown"
    """
    global _stock_market_type_cache
    
    stock_id = normalize_stock_id(stock_id)
    
    # 檢查緩存
    if stock_id in _stock_market_type_cache:
        return _stock_market_type_cache[stock_id]
    
    try:
        response = _make_api_request(
            dataset="TaiwanStockInfo",
            data_id=stock_id
        )
        
        if "data" in response and response["data"]:
            for item in response["data"]:
                if item.get("stock_id") == stock_id:
                    market_type = item.get("type", "unknown")
                    _stock_market_type_cache[stock_id] = market_type
                    return market_type
        
        # 如果找不到，預設為上市
        _stock_market_type_cache[stock_id] = "twse"
        return "twse"
        
    except Exception as e:
        print(f"警告：無法獲取 {stock_id} 的市場類型：{e}")
        # 預設為上市
        return "twse"


def get_yfinance_ticker(stock_id: str) -> str:
    """
    將台股代碼轉換為 Yahoo Finance 格式。
    
    根據市場類型添加適當的後綴：
    - 上市(twse): 加 .TW
    - 上櫃(tpex): 加 .TWO
    - 興櫃(rotc): 加 .TWO
    
    Args:
        stock_id: 台灣股票代碼（例如 "2330"）
        
    Returns:
        str: Yahoo Finance 格式的代碼（例如 "2330.TW"）
    """
    stock_id = normalize_stock_id(stock_id)
    
    # 檢查是否為台股代碼（數字開頭，4-6位）
    if not stock_id or not stock_id[0].isdigit():
        return stock_id  # 非台股，直接返回
    
    if len(stock_id) < 4 or len(stock_id) > 6:
        return stock_id  # 不符合台股格式
    
    # 獲取市場類型
    market_type = get_stock_market_type(stock_id)
    
    if market_type == "twse":
        return f"{stock_id}.TW"
    elif market_type in ["tpex", "rotc"]:
        return f"{stock_id}.TWO"
    else:
        # 預設使用上市後綴
        return f"{stock_id}.TW"


def is_taiwan_stock(stock_id: str) -> bool:
    """
    判斷股票代碼是否為台灣股票。
    
    判斷邏輯：
    - 4-6 位數字開頭
    - 或已有 .TW/.TWO 後綴
    
    Args:
        stock_id: 股票代碼
        
    Returns:
        bool: 是否為台灣股票
    """
    if not stock_id:
        return False
    
    stock_id = stock_id.strip().upper()
    
    # 檢查是否有台股後綴
    if stock_id.endswith(".TW") or stock_id.endswith(".TWO"):
        return True
    
    # 檢查是否為純數字或數字開頭的 4-6 位代碼
    if len(stock_id) >= 4 and len(stock_id) <= 6 and stock_id[0].isdigit():
        return True
    
    return False
