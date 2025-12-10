import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "results")),
    "data_dir": os.path.join(os.path.expanduser("~"), "Documents/Code/ScAI/FR1-data"),
    "data_cache_dir": os.getenv("TRADINGAGENTS_DATA_CACHE_DIR", os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    )),
    # LLM 設定
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5-mini",
    "quick_think_llm": "gpt-5-mini",
    "backend_url": "https://api.openai.com/v1",
    # 辯論與討論設定
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # 資料供應商設定
    # 類別層級設定 (該類別所有工具的預設值)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # 選項: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",  # 選項: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage", # 選項: openai, alpha_vantage, local
        "news_data": "openai",               # 選項: openai, alpha_vantage, google, local
    },
    # 工具層級設定 (優先於類別層級設定)
    "tool_vendors": {
        # 範例: "get_stock_data": "alpha_vantage",  # 覆寫類別預設值
        # 範例: "get_news": "openai",               # 覆寫類別預設值
        "get_global_news": "openai",  # get_global_news 不支持 alpha_vantage，使用 openai 作為主要供應商
    },
}