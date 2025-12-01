import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": os.getenv(
        "TRADINGAGENTS_DATA_DIR",
        os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
            "data",
        ),
    ),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",  # Options: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage", # Options: openai, alpha_vantage, local
        "news_data": "alpha_vantage",        # Options: openai, alpha_vantage, google, local
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        # Example: "get_news": "openai",               # Override category default
    },
    "portfolio_orchestrator": {
        "profile_name": os.getenv("PORTFOLIO_PROFILE_NAME", "Balanced Multi-Asset"),
        "mandate": os.getenv(
            "PORTFOLIO_MANDATE",
            "Preserve capital while capturing medium-term growth opportunities in technology and consumer sectors.",
        ),
        "risk_limits": {
            "max_single_position_pct": float(os.getenv("PORTFOLIO_MAX_POSITION_PCT", "0.15")),
            "max_sector_pct": float(os.getenv("PORTFOLIO_MAX_SECTOR_PCT", "0.35")),
        },
        "notes": os.getenv(
            "PORTFOLIO_NOTES",
            "Prioritize liquid large-cap names. Avoid exceeding buying power and respect existing hedges.",
        ),
        "universe": os.getenv("PORTFOLIO_UNIVERSE", "NVDA,AAPL,MSFT,AMZN,TSLA"),
        "sentiment_lookback_days": int(os.getenv("PORTFOLIO_SENTIMENT_LOOKBACK", "2")),
        "news_headline_limit": int(os.getenv("PORTFOLIO_NEWS_LIMIT", "5")),
        "hypothesis_threshold": float(os.getenv("PORTFOLIO_HYPOTHESIS_THRESHOLD", "0.6")),
        "max_concurrent_hypotheses": int(os.getenv("PORTFOLIO_MAX_HYPOTHESES", "2")),
        "market_data_lookback_days": int(os.getenv("PORTFOLIO_MARKET_LOOKBACK", "30")),
        "trade_activation": {
            "priority_threshold": float(os.getenv("PORTFOLIO_TRADE_PRIORITY_THRESHOLD", "0.8")),
            "min_cash_absolute": float(os.getenv("PORTFOLIO_TRADE_MIN_CASH", "50000")),
            "min_cash_ratio": float(os.getenv("PORTFOLIO_TRADE_MIN_CASH_RATIO", "0.1")),
        },
    },
    "alpaca_mcp": {
        "enabled": os.getenv("ALPACA_MCP_ENABLED", "false").lower() not in ("false", "0", "no"),
        "transport": os.getenv("ALPACA_MCP_TRANSPORT", "http"),
        "host": os.getenv("ALPACA_MCP_HOST", "127.0.0.1"),
        "base_url": os.getenv("ALPACA_MCP_BASE_URL", ""),
        "port": int(os.getenv("ALPACA_MCP_PORT", "8000")),
        "command": os.getenv("ALPACA_MCP_COMMAND", ""),
        "timeout_seconds": float(os.getenv("ALPACA_MCP_TIMEOUT_SECONDS", "30")),
        "required_tools": [
            "get_account_info",
            "get_positions",
            "get_orders",
            "get_market_clock",
        ],
    },
    "trade_execution": {
        "enabled": os.getenv("TRADE_EXECUTION_ENABLED", "false").lower() not in ("false", "0", "no"),
        "dry_run": os.getenv("TRADE_EXECUTION_DRY_RUN", "true").lower() not in ("false", "0", "no"),
        "default_order_quantity": float(os.getenv("TRADE_EXECUTION_DEFAULT_QTY", "10")),
        "time_in_force": os.getenv("TRADE_EXECUTION_TIF", "day"),
    },
    "market_data": {
        "api_key": os.getenv("APCA_API_KEY_ID", ""),
        "secret_key": os.getenv("APCA_API_SECRET_KEY", ""),
        "feed": os.getenv("ALPACA_DATA_FEED", "iex"),
        "news_stream_url": os.getenv("ALPACA_NEWS_STREAM_URL", ""),
    },
    "trading_strategies": {
        "default": os.getenv("TRADINGAGENTS_DEFAULT_STRATEGY", "swing"),
        "presets": {
            "day_trade": {
                "label": "Intraday momentum scalp",
                "horizon_hours": float(os.getenv("TRADINGAGENTS_DAYTRADE_HOURS", "6")),
                "target_pct": float(os.getenv("TRADINGAGENTS_DAYTRADE_TARGET", "0.02")),
                "stop_pct": float(os.getenv("TRADINGAGENTS_DAYTRADE_STOP", "0.01")),
                "follow_up": "close_before_market_close",
                "urgency": "high",
                "success_metric": "Hit target gain within the same session",
                "failure_metric": "Trigger stop or reach session end without target",
                "notes": "Used for rapid intraday reactions; requires strict discipline.",
            },
            "swing": {
                "label": "Multi-day swing trade",
                "horizon_hours": float(os.getenv("TRADINGAGENTS_SWING_HOURS", "72")),
                "target_pct": float(os.getenv("TRADINGAGENTS_SWING_TARGET", "0.04")),
                "stop_pct": float(os.getenv("TRADINGAGENTS_SWING_STOP", "0.02")),
                "follow_up": "reassess_every_close",
                "urgency": "medium",
                "success_metric": "Capture mid-term move within horizon",
                "failure_metric": "Price violates stop or catalyst deteriorates",
                "notes": "Default for most holdings; expects catalysts to resolve within a few days.",
            },
            "position": {
                "label": "Longer-term position build",
                "horizon_hours": float(os.getenv("TRADINGAGENTS_POSITION_HOURS", "336")),
                "target_pct": float(os.getenv("TRADINGAGENTS_POSITION_TARGET", "0.08")),
                "stop_pct": float(os.getenv("TRADINGAGENTS_POSITION_STOP", "0.04")),
                "follow_up": "weekly_review",
                "urgency": "low",
                "success_metric": "Fundamental thesis validated and price reaches target",
                "failure_metric": "Thesis breaks or drawdown exceeds tolerance",
                "notes": "Use for core holdings where narrative spans weeks.",
            },
        },
    },
    "autopilot": {
        "enabled": os.getenv("TRADINGAGENTS_AUTOPILOT", "false").lower() in ("1", "true", "yes"),
        "auto_trade_on_start": os.getenv("AUTOPILOT_SEED_AUTO_TRADE", "true").lower() not in ("false", "0", "no"),
        "event_loop_interval_seconds": int(os.getenv("AUTOPILOT_LOOP_SECONDS", "10")),
        "price_poll_interval_seconds": int(os.getenv("AUTOPILOT_PRICE_POLL_SECONDS", "60")),
        "pre_market_research_minutes": int(os.getenv("AUTOPILOT_PREMARKET_MINUTES", "30")),
    },
    "auto_trade": {
        "max_tickers": int(os.getenv("AUTO_TRADE_MAX_TICKERS", "12")),
        "skip_when_market_closed": os.getenv("AUTO_TRADE_SKIP_WHEN_MARKET_CLOSED", "true").lower()
        not in ("false", "0", "no"),
        "mode": os.getenv("AUTO_TRADE_MODE", "graph"),
        "responses_model": os.getenv("AUTO_TRADE_RESPONSES_MODEL", os.getenv("TRADINGAGENTS_RESPONSES_MODEL", "")),
        "responses_reasoning_effort": os.getenv("AUTO_TRADE_RESPONSES_REASONING", ""),
        "responses_max_turns": int(os.getenv("AUTO_TRADE_RESPONSES_MAX_TURNS", "8")),
        "memory": {
            "enabled": os.getenv("AUTO_TRADE_MEMORY_ENABLED", "true").lower() not in ("false", "0", "no"),
            "dir": os.getenv("AUTO_TRADE_MEMORY_DIR", os.path.join(os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"), "memory")),
            "max_entries": int(os.getenv("AUTO_TRADE_MEMORY_MAX_ENTRIES", "5")),
        },
    },
    "vendor_logging": {
        "verbose": os.getenv("VENDOR_LOG_VERBOSE", "false").lower() in ("1", "true", "yes", "on")
    },
}
