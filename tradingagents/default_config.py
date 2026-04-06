import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": os.path.join(os.path.dirname(__file__), "..", "data"),
    "tickers_file": os.path.join(os.path.dirname(__file__), "..", "data", "tickers.txt"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "google",
    "deep_think_llm": "gemini-3-pro-preview",  # For Google: gemini-2.0-flash or gemini-1.5-pro-latest
    "quick_think_llm": "gemini-2.5-flash-lite",  # For Google: gemini-2.0-flash or gemini-1.5-flash-latest
    "backend_url": "https://api.google.com/v1",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Discovery settings
    "discovery": {
        # ========================================
        # GLOBAL SETTINGS (ranking, analysis, output)
        # ========================================
        "max_candidates_to_analyze": 200,  # Maximum candidates for deep dive analysis
        "analyze_all_candidates": False,  # If True, skip truncation and analyze all candidates
        "final_recommendations": 15,  # Number of final opportunities to recommend
        "deep_dive_max_workers": 1,  # Parallel workers for deep-dive analysis (1 = sequential)
        "discovery_mode": "hybrid",  # "traditional", "semantic", or "hybrid"
        # Ranking context truncation
        "truncate_ranking_context": False,  # True = truncate to save tokens, False = full context
        "max_news_chars": 500,  # Only used if truncate_ranking_context=True
        "max_insider_chars": 300,  # Only used if truncate_ranking_context=True
        "max_recommendations_chars": 300,  # Only used if truncate_ranking_context=True
        # Tool execution logging
        "log_tool_calls": True,  # Capture tool inputs/outputs to results logs
        "log_tool_calls_console": False,  # Mirror tool logs to Python logger
        "log_prompts_console": False,  # Show LLM prompts in console (always saved to log file)
        "tool_log_max_chars": 10_000,  # Max chars stored per tool output
        "tool_log_exclude": ["validate_ticker"],  # Tool names to exclude from logging
        # Console price charts (output formatting)
        "console_price_charts": True,  # Render mini price charts in console output
        "price_chart_library": "plotille",  # "plotille" (prettier) or "plotext" fallback
        "price_chart_windows": ["1d", "7d", "1m", "6m", "1y"],  # Windows to render
        "price_chart_lookback_days": 30,  # Lookback window for charts
        "price_chart_width": 60,  # Chart width (characters)
        "price_chart_height": 12,  # Chart height (rows)
        "price_chart_max_tickers": 10,  # Max tickers to chart per run
        "price_chart_show_movement_stats": True,  # Show movement stats in console
        # ========================================
        # FILTER STAGE SETTINGS
        # ========================================
        "filters": {
            # Liquidity filter
            "min_average_volume": 500_000,  # Minimum average volume
            "volume_lookback_days": 10,  # Days to average for liquidity check
            # Same-day mover filter (remove stocks that already moved today)
            "filter_same_day_movers": True,  # Enable/disable filter
            "intraday_movement_threshold": 10.0,  # Intraday % change threshold
            # Recent mover filter (remove stocks that moved in recent days)
            "filter_recent_movers": True,  # Enable/disable filter
            "recent_movement_lookback_days": 7,  # Days to check for recent moves
            "recent_movement_threshold": 10.0,  # % change threshold
            "recent_mover_action": "filter",  # "filter" or "deprioritize"
            # Volume / compression detection
            "volume_cache_key": "default",  # Cache key for volume data
            "min_market_cap": 0,  # Minimum market cap in billions (0 = no filter)
            "compression_atr_pct_max": 2.0,  # Max ATR % for compression detection
            "compression_bb_width_max": 6.0,  # Max Bollinger bandwidth for compression
            "compression_min_volume_ratio": 1.3,  # Min volume ratio for compression
        },
        # ========================================
        # ENRICHMENT STAGE SETTINGS
        # ========================================
        "enrichment": {
            "batch_news_vendor": "google",  # Vendor for batch news: "openai" or "google"
            "batch_news_batch_size": 150,  # Tickers per API call
            "news_lookback_days": 0.5,  # Days of news history for enrichment
            "context_max_snippets": 2,  # Max news snippets per candidate
            "context_snippet_max_chars": 140,  # Max chars per snippet
        },
        # ========================================
        # PIPELINES (priority and budget per pipeline)
        # ========================================
        "pipelines": {
            "edge": {
                "enabled": True,
                "priority": 1,
                "ranker_prompt": "edge_signals_ranker.txt",
                "deep_dive_budget": 15,
            },
            "momentum": {
                "enabled": True,
                "priority": 2,
                "ranker_prompt": "momentum_ranker.txt",
                "deep_dive_budget": 10,
            },
            "news": {
                "enabled": True,
                "priority": 3,
                "ranker_prompt": "news_catalyst_ranker.txt",
                "deep_dive_budget": 5,
            },
            "social": {
                "enabled": True,
                "priority": 4,
                "ranker_prompt": "social_signals_ranker.txt",
                "deep_dive_budget": 5,
            },
            "events": {"enabled": True, "priority": 5, "deep_dive_budget": 3},
        },
        # ========================================
        # SCANNER EXECUTION SETTINGS
        # ========================================
        "scanner_execution": {
            "concurrent": True,  # Run scanners in parallel
            "max_workers": 8,  # Max concurrent scanner threads
            "timeout_seconds": 30,  # Timeout per scanner
        },
        # ========================================
        # SCANNERS (each with scanner-specific settings)
        # ========================================
        "scanners": {
            # Edge signals - Early information advantages
            "insider_buying": {
                "enabled": True,
                "pipeline": "edge",
                "limit": 20,
                "lookback_days": 7,  # Days to look back for insider purchases
                "min_transaction_value": 25000,  # Minimum transaction value ($) to consider
            },
            "options_flow": {
                "enabled": True,
                "pipeline": "edge",
                "limit": 15,
                "unusual_volume_multiple": 2.0,  # Min volume/OI ratio for unusual activity
                "min_premium": 25000,  # Minimum premium ($) to filter noise
                "min_volume": 1000,  # Minimum option volume to consider
                # ticker_file: path to ticker list (defaults to tickers_file from root config)
                # ticker_universe: explicit list overrides ticker_file if set
                "max_tickers": 1000,  # Max tickers to scan (from start of file)
                "max_workers": 8,  # Parallel option chain fetch threads
            },
            "congress_trades": {
                "enabled": False,
                "pipeline": "edge",
                "limit": 10,
                "lookback_days": 7,  # Days to look back for congressional trades
            },
            # Momentum - Price and volume signals
            "volume_accumulation": {
                "enabled": True,
                "pipeline": "momentum",
                "limit": 15,
                "unusual_volume_multiple": 2.0,  # Min volume multiple vs average
                "volume_cache_key": "default",  # Cache key for volume data
                "compression_atr_pct_max": 2.0,  # Max ATR % for compression detection
                "compression_bb_width_max": 6.0,  # Max Bollinger bandwidth for compression
                "compression_min_volume_ratio": 1.3,  # Min volume ratio for compression
            },
            "market_movers": {
                "enabled": False,
                "pipeline": "momentum",
                "limit": 10,
            },
            # News - Catalyst-driven signals
            "semantic_news": {
                "enabled": True,
                "pipeline": "news",
                "limit": 10,
                "sources": ["google_news", "sec_filings", "alpha_vantage", "gemini_search"],
                "lookback_hours": 6,  # How far back to look for news
                "min_news_importance": 5,  # Minimum news importance score (1-10)
                "min_similarity": 0.5,  # Minimum similarity for ticker matching
                "max_tickers_per_news": 3,  # Max tickers to match per news item
                "news_lookback_days": 0.5,  # Days of news history to analyze
            },
            "analyst_upgrade": {
                "enabled": True,
                "pipeline": "news",
                "limit": 5,
                "lookback_days": 1,  # Days to look back for rating changes
            },
            # Social - Community signals
            "reddit_trending": {
                "enabled": True,
                "pipeline": "social",
                "limit": 15,
            },
            "reddit_dd": {
                "enabled": True,
                "pipeline": "social",
                "limit": 10,
            },
            # Events - Calendar-based signals
            "earnings_calendar": {
                "enabled": True,
                "pipeline": "events",
                "limit": 10,
                "max_candidates": 25,  # Hard cap on earnings candidates
                "max_days_until_earnings": 7,  # Only include earnings within N days
                "min_market_cap": 0,  # Minimum market cap in billions (0 = no filter)
            },
            "short_squeeze": {
                "enabled": True,
                "pipeline": "events",
                "limit": 5,
                "min_short_interest_pct": 15.0,  # Minimum short interest %
                "min_days_to_cover": 5.0,  # Minimum days to cover ratio
            },
            "ml_signal": {
                "enabled": True,
                "pipeline": "momentum",
                "limit": 15,
                "min_win_prob": 0.35,  # Minimum P(WIN) to surface as candidate
                "lookback_period": "6mo",  # OHLCV history to fetch (needs ~130 trading days)
                # ticker_file: path to ticker list (defaults to tickers_file from root config)
                # ticker_universe: explicit list overrides ticker_file if set
                "fetch_market_cap": False,  # Skip for speed (1 NaN out of 30 features)
                "max_workers": 8,  # Parallel feature computation threads
            },
            "minervini": {
                "enabled": True,
                "pipeline": "momentum",
                "limit": 10,
                "min_rs_rating": 70,  # Min IBD-style RS Rating (0-100)
                "lookback_period": "1y",  # Needs 200 trading days for SMA200
                "sma_200_slope_days": 20,  # Days back to check SMA200 slope
                "min_pct_off_low": 30,  # Must be 30%+ above 52w low
                "max_pct_from_high": 25,  # Must be within 25% of 52w high
            },
        },
    },
    # Memory settings
    "enable_memory": False,  # Enable/disable embeddings and memory system
    "load_historical_memories": False,  # Load pre-built historical memories on startup
    "memory_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "data/memories"
    ),  # Directory for saved memories
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",  # Options: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",  # Options: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage",  # Options: openai, alpha_vantage, local
        "news_data": "reddit,alpha_vantage",  # Options: openai, alpha_vantage, google, reddit, local
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Discovery tools - each tool supports only one vendor
        "get_trending_tickers": "reddit",  # Reddit trending stocks
        "get_market_movers": "alpha_vantage",  # Top gainers/losers
        # "get_tweets": "twitter",  # Twitter API
        # "get_tweets_from_user": "twitter",  # Twitter API
        "get_recommendation_trends": "finnhub",  # Analyst recommendations
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        # Example: "get_news": "openai",               # Override category default
    },
}
