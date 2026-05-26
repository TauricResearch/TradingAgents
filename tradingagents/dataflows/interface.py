"""
数据流程接口层 —— 统一多供应商数据源的访问入口

在项目中的角色：作为数据访问层的门面（Facade），将 yfinance、Alpha Vantage 等不同数据源的实现
统一到一致的 API 接口下，支持配置化路由和故障降级。

设计模式：
- 门面模式（Facade）：对外暴露统一的工具调用接口
- 策略模式（Strategy）：不同供应商作为可替换的策略
- 故障降级：遇到限流时自动切换到备用供应商

关键依赖：
上游：配置模块 config.py
下游：y_finance.py, yfinance_news.py, alpha_vantage.py

调用链示例：
    route_to_vendor("get_stock_data", symbol="AAPL")
        → get_category_for_method("get_stock_data") → "core_stock_apis"
        → get_vendor("core_stock_apis", "get_stock_data") → "yfinance"
        → VENDOR_METHODS["get_stock_data"]["yfinance"] → get_YFin_data_online
        → 返回股票数据
"""
from typing import Annotated

# 导入各供应商的具体实现
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError

# Configuration and routing logic
from .config import get_config

# 工具按功能分类，用于配置和路由时的类别查找
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    }
}

# 支持的供应商列表
VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
]

# 方法名到供应商实现的映射表
# 结构：{方法名: {供应商名: 实现函数}}
# 实现函数可以是单个函数，也可以是列表形式（用于特殊处理）
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
}

def get_category_for_method(method: str) -> str:
    """根据方法名查找所属的工具分类。

    Args:
        method: 方法名称，如 "get_stock_data"

    Returns:
        分类名称，如 "core_stock_apis"

    Raises:
        ValueError: 方法不在任何分类中时抛出
    """
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """获取指定分类或方法的配置供应商。

    优先级：方法级配置 > 分类级配置 > 默认值

    Args:
        category: 工具分类名称
        method: 可选，方法名称（用于优先查找方法级配置）

    Returns:
        供应商名称，支持逗号分隔的多个供应商（如 "yfinance,alpha_vantage"）
    """
    config = get_config()

    # 优先检查方法级配置（粒度更细）
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # 降级到分类级配置
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """核心路由函数：将方法调用路由到配置的供应商实现，并支持故障降级。

    执行流程：
    1. 根据方法名查找所属分类
    2. 获取配置的供应商列表（支持逗号分隔的多个供应商）
    3. 构建降级链：配置的供应商优先，然后补充其他可用供应商
    4. 依次尝试每个供应商，遇到限流错误时自动降级到下一个
    5. 所有供应商都失败时抛出异常

    Args:
        method: 要调用的方法名称
        *args: 位置参数，传递给具体实现
        **kwargs: 关键字参数，传递给具体实现

    Returns:
        具体供应商实现返回的数据

    Raises:
        ValueError: 方法不支持时抛出
        RuntimeError: 所有供应商都不可用时抛出
    """
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # 构建降级链：配置的供应商优先，然后补充其他可用供应商
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        # 处理实现函数可能是列表的情况（预留扩展能力）
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except AlphaVantageRateLimitError:
            # 仅限流错误触发降级，其他异常直接抛出
            continue

    raise RuntimeError(f"No available vendor for '{method}'")