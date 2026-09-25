import os
import tempfile
from pathlib import Path

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")
def get_default_cache_dir() -> str:
    """Return a writable cache directory across local and Docker environments."""

    env_path = os.getenv("TRADINGAGENTS_CACHE_DIR")
    if env_path:
        return env_path

    candidate = Path(_TRADINGAGENTS_HOME) / "cache"

    try:
        candidate.mkdir(parents=True, exist_ok=True)
        test_file = candidate / ".write_test"
        test_file.touch(exist_ok=True)
        test_file.unlink(missing_ok=True)
        return str(candidate)
    except Exception:
        pass

    fallback = Path(tempfile.gettempdir()) / "tradingagents" / "cache"
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": get_default_cache_dir(),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    "market_type": "stock",
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Benchmark used for alpha calculation in deferred reflection.
    # When `benchmark_ticker` is set, it wins for every analysis.
    # Otherwise the longest matching suffix in `benchmark_map` is used,
    # falling back to the "" entry for tickers without a known suffix.
    "benchmark_ticker": None,
    "benchmark_map": {
        ".NS": "^NSEI",     # Nifty 50 (NSE India)
        ".BO": "^BSESN",    # Sensex (BSE India)
        ".T":  "^N225",     # Nikkei 225 (Japan)
        ".HK": "^HSI",      # Hang Seng (Hong Kong)
        ".L":  "^FTSE",     # FTSE 100 (London)
        ".TO": "^GSPTSE",   # TSX Composite (Toronto)
        "":    "SPY",       # default for US-listed tickers
    },
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # ── News / data fetching parameters ───────────────────────────────────
    # Maximum number of articles fetched per ticker (ticker-specific news).
    # Increase for longer lookback strategies; decrease to reduce token usage.
    "news_article_limit": 20,
    # Number of days to look back when fetching ticker-specific news.
    "news_lookback_days": 7,
    # Maximum number of articles fetched for global/macro news.
    "global_news_article_limit": 10,
    # Number of days to look back for global/macro news.
    "global_news_lookback_days": 7,
    # Search queries used by get_global_news to pull macro headlines.
    # Extend or replace this list to broaden geographic/sector coverage.
    "global_news_queries": [
        "Federal Reserve interest rates inflation",
        "S&P 500 earnings GDP economic outlook",
        "geopolitical risk trade war sanctions",
        "ECB Bank of England BOJ central bank policy",
        "oil commodities supply chain energy",
    ],
    # ──────────────────────────────────────────────────────────────────────
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        "sentiment_data": "default",        # Reddit, Fear&Greed, Discord UW (no vendor alt)
        "macro_data": "fred",               # Options: fred
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}


CRYPTO_TRAIN_CONFIG = {
    **DEFAULT_CONFIG,
    # Train mode: crypto-only, low-cost Gemini Flash, no third/global memory tier.
    "market_type": "crypto",
    "train_mode": True,
    "llm_provider": "google",
    "deep_think_llm": "gemini-2.5-flash",
    "quick_think_llm": "gemini-2.5-flash-lite",
    "google_thinking_level": "minimal",
    "google_api_keys": os.getenv("GOOGLE_API_KEYS", ""),
    "google_key_rotation_state_path": os.getenv(
        "TRADINGAGENTS_GOOGLE_ROTATION_STATE",
        os.path.join(_TRADINGAGENTS_HOME, "crypto_memory", "google_key_rotation.json"),
    ),
    "output_language": "Vietnamese",
    "selected_analysts": ["market", "news", "social"],
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "benchmark_ticker": "BTC/USDT",
    # Two-tier memory only: raw + lesson.
    "memory_backend": "crypto_two_tier",
    "crypto_memory_dir": os.getenv(
        "TRADINGAGENTS_CRYPTO_MEMORY_DIR",
        os.path.join(_TRADINGAGENTS_HOME, "crypto_memory"),
    ),
    "crypto_lesson_context_limit": 8,
    "crypto_training_memory_tiers": ["lesson"],
    # Binance / ccxt public data.
    "crypto_exchange": "binance",
    "crypto_market_type": "spot",
    "crypto_timeframe": "15m",
    "crypto_ohlcv_limit": 240,
    "crypto_report_rows": 80,
    "crypto_indicator_rows": 40,
    "crypto_watchlist": ["BTC/USDT", "ETH/USDT"],
    "train_trigger_minutes": 15,
    # Scanner defaults: conservative crypto filters optimized for paper-trade safety.
    "scanner_timeframe": "1h",           # Use 1h candles for RSI (more meaningful for swing entries)
    "scanner_enable_rsi_reversal": True,
    "scanner_enable_breakout": False,
    "scanner_enable_ema_crossover": False,
    "scanner_enable_rsi_momentum": False,
    "scanner_enable_trend_pullback": False,
    "scanner_enable_liquidity_sweep": True,
    "scanner_enable_range_bounce": True,
    "scanner_enable_bb_reversion": True,
    "scanner_enable_orderflow": False,
    "scanner_enable_regime_flip": False,
    "scanner_enable_ensemble": True,
    "scanner_ensemble_min_votes": 3,
    "scanner_ensemble_base_bonus": 0.05,
    "scanner_ensemble_max_bonus": 0.12,
    "scanner_liquidity_sweep_lookback": 20,
    "scanner_range_lookback": 20,
    "scanner_range_bounce_max_pos": 0.35,
    "scanner_range_min_width_atr": 1.6,
    "scanner_range_min_volume_spike": 0.20,
    "scanner_sideway_min_rsi": 28,
    "scanner_sideway_max_rsi": 65,
    "scanner_orderflow_lookback": 8,
    "scanner_regime_flip_lookback": 8,
    "scanner_reversal_buy_regimes": ["trend_up", "trend_down", "sideway"],
    "scanner_reversal_sell_regimes": [],
    # Timeframes to scan in parallel.  The scanner checks every timeframe and
    # keeps the best signal per symbol.  More timeframes = more signals, but
    # also more API calls.  Set to a single-element list to restore the old
    # single-timeframe behaviour.
    "scanner_timeframes": ["15m", "30m", "1h"],
    "scanner_rsi_oversold": 35,   # calibrated for stockstats Wilder RSI on 1h timeframe
    "scanner_max_reversal_rsi": 35,
    "scanner_max_breakout_rsi": 68,
    "scanner_min_momentum_volume_spike": 0.50,
    "scanner_min_strength": 0.65,
    "scanner_min_reward_risk": 1.20,
    "scanner_rsi_extreme": 25,
    "data_vendors": {
        "core_stock_apis": "binance",
        "technical_indicators": "binance",
        "fundamental_data": "yfinance",
        "news_data": "crypto",
        "sentiment_data": "crypto",
    },
    "tool_vendors": {},
}
