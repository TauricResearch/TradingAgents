import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.2",
    "quick_think_llm": "gpt-5-mini",
    "backend_url": "https://api.openai.com/v1",
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    # Graph settings
    "max_recur_limit": 100,
    # Swing trading settings
    "market": "KRX",  # "KRX" or "US"
    "swing_hold_days_min": 2,
    "swing_hold_days_max": 20,
    # Portfolio settings
    "portfolio_id": "default",
    "total_capital": 100_000_000,  # 1억원 (KRX) or $100,000 (US)
    "max_positions": 5,
    "max_position_pct": 0.20,  # 20% of total capital per position
    "default_stop_loss_pct": 0.05,  # 5%
    "default_take_profit_pct": 0.15,  # 15%
    # Screening settings
    "screening_min_market_cap": 500_000_000_000,  # 5000억원
    "screening_min_volume": 100_000,
    "screening_max_candidates": 5,
    "us_universe": "sp500",  # "sp500", "nasdaq100", or "custom"
    "custom_watchlist": [],  # custom ticker list for manual universe
    # Broker settings (Kiwoom Securities REST API)
    "broker_enabled": False,  # True to enable order execution
    "broker_dry_run": True,   # True = validate only, False = real orders
    "kiwoom_app_key": os.getenv("KIWOOM_APP_KEY", ""),
    "kiwoom_app_secret": os.getenv("KIWOOM_APP_SECRET", ""),
    "kiwoom_account_no": os.getenv("KIWOOM_ACCOUNT_NO", ""),
    "kiwoom_is_paper": True,  # True = 모의투자, False = 실전투자
    # Data vendor configuration
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
        # Korean market data vendors
        "krx_stock_apis": "krx",
        "korean_market_data": "krx",
        "korean_fundamental_data": "krx",
        "korean_news_data": "naver",
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        "get_dart_financials": "dart",
        "get_dart_disclosures": "dart",
        "get_dart_shareholders": "dart",
    },
}
