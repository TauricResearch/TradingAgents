from typing import Annotated

# 從特定供應商的模組匯入
from .local import get_YFin_data, get_finnhub_news, get_finnhub_company_insider_sentiment, get_finnhub_company_insider_transactions, get_simfin_balance_sheet, get_simfin_cashflow, get_simfin_income_statements, get_reddit_global_news, get_reddit_company_news
from .y_finance import get_YFin_data_online, get_stock_stats_indicators_window, get_balance_sheet as get_yfinance_balance_sheet, get_cashflow as get_yfinance_cashflow, get_income_statement as get_yfinance_income_statement, get_insider_transactions as get_yfinance_insider_transactions, get_fundamentals as get_yfinance_fundamentals
from .google import get_google_news
from .openai import get_stock_news_openai, get_global_news_openai, get_fundamentals_openai
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news
)
from .alpha_vantage_common import AlphaVantageRateLimitError

# 設定和路由邏輯
from .config import get_config

# 按類別組織的工具
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV 股價數據",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "技術分析指標",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "公司基本面",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "新聞 (公開/內部人士，原始/處理後)",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_sentiment",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "local",
    "yfinance",
    "openai",
    "google"
]

# 方法與其特定供應商實現的映射
VENDOR_METHODS = {
    # 核心股票 API
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "local": get_YFin_data,
    },
    # 技術指標
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
        "local": get_stock_stats_indicators_window
    },
    # 基本面數據
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "openai": get_fundamentals_openai,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
        "local": get_simfin_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
        "local": get_simfin_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
        "local": get_simfin_income_statements,
    },
    # 新聞數據
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "openai": get_stock_news_openai,
        "google": get_google_news,
        "local": [get_finnhub_news, get_reddit_company_news, get_google_news],
    },
    "get_global_news": {
        "openai": get_global_news_openai,
        "local": get_reddit_global_news
    },
    "get_insider_sentiment": {
        "local": get_finnhub_company_insider_sentiment
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
        "local": get_finnhub_company_insider_transactions,
    },
}

def get_category_for_method(method: str) -> str:
    """獲取包含指定方法的類別。"""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"在任何類別中都找不到方法 '{method}'")

def get_vendor(category: str, method: str = None) -> str:
    """
    獲取數據類別或特定工具方法的已設定供應商。
    工具級別的設定優先於類別級別。
    """
    config = get_config()

    # 首先檢查工具級別的設定 (如果提供了方法)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # 回退到類別級別的設定
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """將方法調用路由到具有備援支援的適當供應商實現。"""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)

    # 處理以逗號分隔的供應商
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"不支援方法 '{method}'")

    # 獲取此方法所有可用供應商以進行備援
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    
    # 建立備援供應商列表：主要供應商優先，然後是其餘供應商作為備援
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    # 調試：打印備援順序
    primary_str = " → ".join(primary_vendors)
    fallback_str = " → ".join(fallback_vendors)
    print(f"調試：{method} - 主要：[{primary_str}] | 完整備援順序：[{fallback_str}]")

    # 追蹤結果和執行狀態
    results = []
    vendor_attempt_count = 0
    any_primary_vendor_attempted = False
    successful_vendor = None

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            if vendor in primary_vendors:
                print(f"資訊：方法 '{method}' 不支援供應商 '{vendor}'，將備援至下一個供應商")
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        is_primary_vendor = vendor in primary_vendors
        vendor_attempt_count += 1

        # 追蹤是否嘗試了任何主要供應商
        if is_primary_vendor:
            any_primary_vendor_attempted = True

        # 調試：打印當前嘗試
        vendor_type = "主要" if is_primary_vendor else "備援"
        print(f"調試：正在為 {method} 嘗試 {vendor_type} 供應商 '{vendor}' (第 {vendor_attempt_count} 次嘗試)")

        # 處理供應商的方法列表
        if isinstance(vendor_impl, list):
            vendor_methods = [(impl, vendor) for impl in vendor_impl]
            print(f"調試：供應商 '{vendor}' 有多個實現：{len(vendor_methods)} 個函式")
        else:
            vendor_methods = [(vendor_impl, vendor)]

        # 運行此供應商的方法
        vendor_results = []
        for impl_func, vendor_name in vendor_methods:
            try:
                print(f"調試：正在從供應商 '{vendor_name}' 調用 {impl_func.__name__}...")
                
                # 執行函數（已由各供應商內部處理timeout）
                result = impl_func(*args, **kwargs)
                vendor_results.append(result)
                print(f"成功：來自供應商 '{vendor_name}' 的 {impl_func.__name__} 成功完成")
                    
            except AlphaVantageRateLimitError as e:
                if vendor == "alpha_vantage":
                    print(f"速率限制：超過 Alpha Vantage 速率限制，將備援至下一個可用供應商")
                    print(f"調試：速率限制詳細資訊：{e}")
                # 繼續到下一個供應商進行備援
                continue
            except Exception as e:
                # 記錄詳細錯誤但繼續其他實現
                error_type = type(e).__name__
                print(f"失敗：來自供應商 '{vendor_name}' 的 {impl_func.__name__} 失敗 ({error_type}): {e}")
                continue

        # 新增此供應商的結果
        if vendor_results:
            results.extend(vendor_results)
            successful_vendor = vendor
            result_summary = f"獲得 {len(vendor_results)} 個結果"
            print(f"成功：供應商 '{vendor}' 成功 - {result_summary}")
            
            # 停止邏輯：對於單一供應商設定，在第一個成功的供應商後停止
            # 多供應商設定 (以逗號分隔) 可能希望從多個來源收集
            if len(primary_vendors) == 1:
                print(f"調試：在成功的供應商 '{vendor}' 後停止 (單一供應商設定)")
                break
        else:
            print(f"失敗：供應商 '{vendor}' 未產生任何結果")

    # 最終結果摘要
    if not results:
        print(f"失敗：方法 '{method}' 的所有 {vendor_attempt_count} 次供應商嘗試均失敗")
        raise RuntimeError(f"方法 '{method}' 的所有供應商實現均失敗")
    else:
        print(f"最終：方法 '{method}' 在 {vendor_attempt_count} 次供應商嘗試後，以 {len(results)} 個結果完成")

    # 如果只有一個結果，則返回單個結果，否則連接為字串
    if len(results) == 1:
        return results[0]
    else:
        # 將所有結果轉換為字串並連接
        return '\n'.join(str(result) for result in results)
