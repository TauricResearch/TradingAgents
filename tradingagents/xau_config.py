from tradingagents.default_config import DEFAULT_CONFIG

# Create a deep copy to avoid modifying the original default config
XAU_CONFIG = {
    **DEFAULT_CONFIG,
    "asset_class": "commodity",
    "trading_hours": "24/5",
    "tick_size": 0.01,
    "contract_size": 100,  # oz for futures
    "max_leverage": 50,
    "max_position_size_pct": 2.0,
    "atr_multiplier_stop": 2.5,
    "correlation_threshold": -0.6,
}

# Override data vendors for XAU-specific sources
XAU_CONFIG["data_vendors"] = {
    **DEFAULT_CONFIG["data_vendors"],
    "core_stock_apis": "yfinance",          # For XAU/USD price data (GC=F)
    "technical_indicators": "yfinance",
    "macro_data": "fred",                 # NEW: FRED for macro
    "positioning_data": "cot_api",        # NEW: COT data
    "etf_data": "yfinance",               # NEW: ETF flows via yfinance
    # Override equity-specific vendors
    "fundamental_data": "fred",           # Gold uses macro data, not company fundamentals
    "news_data": "alpha_vantage",         # Can still use for general market news
}

# Define the specialized analyst team for XAU
XAU_CONFIG["analyst_team"] = [
    "xau_market",
    "xau_macro",
    "xau_news",
    "xau_positioning",
]