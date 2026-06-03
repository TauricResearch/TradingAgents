import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

# Single source of truth for env-var → config-key overrides. To expose
# a new config key for environment-based override, add a row here — no
# entry-point script changes required. Coercion is driven by the type
# of the existing default, so users can keep writing plain strings in
# their .env file.
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER":         "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM":       "deep_think_llm",
    "TRADINGAGENTS_QUICK_THINK_LLM":      "quick_think_llm",
    "TRADINGAGENTS_LLM_BACKEND_URL":      "backend_url",
    "TRADINGAGENTS_OUTPUT_LANGUAGE":      "output_language",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS":    "max_debate_rounds",
    "TRADINGAGENTS_MAX_RISK_ROUNDS":      "max_risk_discuss_rounds",
    "TRADINGAGENTS_CHECKPOINT_ENABLED":   "checkpoint_enabled",
    "TRADINGAGENTS_BENCHMARK_TICKER":     "benchmark_ticker",
    "TRADINGAGENTS_DEEPSEEK_REASONING_EFFORT": "deepseek_reasoning_effort",
    "TRADINGAGENTS_IIC_DB_PATH":          "iic_db_path",
    "TRADINGAGENTS_IIC_DATA_DIR":         "iic_data_dir",
    "TRADINGAGENTS_COST_GUARD_ENABLED":   "cost_guard_enabled",
    "TRADINGAGENTS_ORCHESTRATOR_ENABLED": "orchestrator_enabled",
}


def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value."""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """Apply TRADINGAGENTS_* env vars to the config dict in-place."""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        config[key] = _coerce(raw, config.get(key))
    return config


def _apply_nested_env_overrides(config: dict) -> dict:
    """Custom (non-flat) env overrides that don't fit the _ENV_OVERRIDES table.

    Handles:
    - TELEGRAM_BOT_ALLOWED_CHAT_IDS: comma-separated numeric Telegram chat ids
      (.env, never committed) → telegram_bot.allowed_chat_ids as list[int].
      Empty/unset → leave the committed default ([] = deny-all) untouched.
    - TELEGRAM_SENSING_CHANNELS: comma-separated public channel usernames the
      sensing telegram adapter listens to (.env) → telegram_channels as
      list[str]. A leading '@' is stripped from each. Empty/unset → leave the
      committed default ([] = listen to nothing) untouched.
    """
    raw = os.environ.get("TELEGRAM_BOT_ALLOWED_CHAT_IDS")
    if raw is not None and raw.strip() != "":
        chat_ids = [int(tok.strip()) for tok in raw.split(",") if tok.strip()]
        config.setdefault("telegram_bot", {})["allowed_chat_ids"] = chat_ids

    chans = os.environ.get("TELEGRAM_SENSING_CHANNELS")
    if chans is not None and chans.strip() != "":
        config["telegram_channels"] = [
            tok.strip().lstrip("@") for tok in chans.split(",") if tok.strip()
        ]
    return config


DEFAULT_CONFIG = _apply_nested_env_overrides(_apply_env_overrides({
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # IIC-FORGE F1 — persistence + data layout
    "iic_db_path": os.path.join(_TRADINGAGENTS_HOME, "iic.db"),
    "iic_data_dir": os.path.join(_TRADINGAGENTS_HOME, "data"),
    # IIC-FORGE F1 — cost guards (coded but disabled by default — see
    # docs/superpowers/specs/2026-05-25-iic-forge-program-design.md Appendix A).
    "cost_guard_enabled": False,
    # IIC-FORGE F3 — always-on sensing + triage
    "sensing_redis_url": "redis://127.0.0.1:6379/0",
    "sensing_ingest_stream": "ingest:raw",
    "sensing_consumer_group": "triage",
    "sensing_dead_stream": "ingest:dead",
    "sensing_triage_consumers": 4,
    "sensing_triage_max_failures": 5,
    "sensing_dedupe_cosine_threshold": 0.92,
    "sensing_dedupe_window_hours": 24,
    "sensing_fingerprint_ttl_hours": 72,
    "sensing_watchlist_salience_threshold": 0.7,
    "sensing_watchlist_confidence_threshold": 0.8,
    "sensing_watchlist_ttl_days": 7,
    "sensing_watchlist_refresh_seconds": 60,
    "sensing_salience_cache_ttl_seconds": 86400,
    "sensing_embedder_model": "sentence-transformers/all-MiniLM-L6-v2",
    "sensing_adapters_enabled": {
        "polygon_news": True,
        "telegram": True,
        "rss": True,
        "gdelt": True,
        "macro": True,
        "x": False,   # off by default per spec D8 / R-F3-3
    },
    # IIC-FORGE F4 — autonomous trigger loop (orchestrator)
    "orchestrator_enabled": False,
    "promoter_poll_interval_s": 10,
    "promoter_batch_size": 50,
    "alert_cooldown_min": 60,
    "alert_salience_threshold": 0.85,
    "alert_ticker_confidence_threshold": 0.9,
    # F4 approval gate (IIC-FORGE-09): light alert → approve → study.
    # When False, the promoter would fall back to the legacy auto-enqueue path
    # (kept only as an escape hatch; default behavior is the gate).
    "alert_approval_gate_enabled": True,
    # How long a pending run_full_study approval stays valid (1 day per spec §4).
    "alert_pending_ttl_hours": 24,
    "alert_quality_threshold": 0.80,
    "worker_poll_interval_s": 2,
    "worker_job_timeout_min": 20,
    "max_concurrent_jobs": 1,
    # Cost guards (program-spec Appendix A: enabled=False during F0–F5)
    "trigger_backpressure_enabled": False,
    "trigger_backpressure_max_pending": 20,
    "trigger_daily_rate_enabled": False,
    "trigger_daily_rate_max_jobs": 200,
    "daily_budget_enabled": False,
    "daily_budget_usd": 10.0,
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "deepseek",
    "deep_think_llm": "deepseek-v4-pro",     # V4 thinking flagship; deep reasoning / synthesis (effort=max)
    "quick_think_llm": "deepseek-v4-flash",  # V4 thinking fast model; analyst tool loops (default effort)
    "default_analysis_persona_id": "balanced",
    "committee_persona_ids": ["value", "momentum", "macro"],
    "committee_mode_enabled": False,
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": "max",    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    "deepseek_reasoning_effort": "max",            # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 3,
    "max_risk_discuss_rounds": 3,
    "max_recur_limit": 100,
    "analyst_concurrency_limit": 5,
    # News / data fetching parameters
    # Increase for longer lookback strategies or to broaden macro coverage;
    # decrease to reduce token usage in agent prompts.
    "news_article_limit": 20,             # max articles per ticker (ticker-news)
    "global_news_article_limit": 12,      # max articles for global/macro news
    "global_news_lookback_days": 7,       # macro news lookback window
    # Search queries used by get_global_news for macro headlines. Extend or
    # replace to broaden geographic / sector coverage.
    "global_news_queries": [
        "Federal Reserve interest rates inflation",
        "S&P 500 earnings GDP economic outlook",
        "geopolitical risk trade war sanctions",
        "ECB Bank of England BOJ central bank policy",
        "oil commodities supply chain energy",
    ],
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        "options_data": "yfinance",          # Options: yfinance (Polygon/Futu via Epic B fallback chain)
        "osint_social": "telegram",          # Options: telegram (Telegram); X tool routes to "x" vendor automatically
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Futu OpenD gateway (Epic B). The daemon must be running and logged in;
    # leave the host/port at defaults unless OpenD is on a different machine.
    "futu_opend_host": "127.0.0.1",
    "futu_opend_port": 11111,
    # Curated Telegram channels for OSINT digest (Epic B). Add `@handle`
    # entries; balance regions deliberately.
    "telegram_channels": [],
    # Benchmark for alpha calculation in the reflection layer.
    # ``benchmark_ticker`` (when set) overrides the suffix map for all
    # tickers; leave it None to use ``benchmark_map`` for auto-detection
    # based on the ticker's exchange suffix. SPY remains the US default
    # so the reflection label keeps reading "Alpha vs SPY" for US tickers
    # while non-US tickers get their regional index automatically.
    "benchmark_ticker": None,
    "benchmark_map": {
        ".NS":  "^NSEI",    # NSE India (Nifty 50)
        ".BO":  "^BSESN",   # BSE India (Sensex)
        ".T":   "^N225",    # Tokyo (Nikkei 225)
        ".HK":  "^HSI",     # Hong Kong (Hang Seng)
        ".L":   "^FTSE",    # London (FTSE 100)
        ".TO":  "^GSPTSE",  # Toronto (TSX Composite)
        ".AX":  "^AXJO",    # Australia (ASX 200)
        "":     "SPY",      # default for US-listed tickers (no suffix)
    },
    # ============================================================
    # F5 — Delivery + operations
    # ============================================================
    "delivery": {
        "enabled_channels": ["email", "cli"],
        "quiet_hours": {
            "enabled": True,
            "start": "22:00",
            "end": "07:00",
        },
        "digest_modes": {
            "telegram": "terse",
            "email": "full",
            "cli": "full",
        },
    },
    "telegram_bot": {
        "enabled": True,
        # Committed default is empty = deny-all (restricted). Populate at
        # runtime from the TELEGRAM_BOT_ALLOWED_CHAT_IDS env var (.env), a
        # comma-separated list of numeric chat ids — see the override applied
        # after _apply_env_overrides below. Never commit real chat ids here.
        "allowed_chat_ids": [],
        "poll_interval_seconds": 1,
    },
    # F5 delivery: how long a pending Telegram/email action (e.g. an awaiting
    # confirmation) stays valid before the delivery agent expires it.
    "brief_action_ttl_hours": 24,
    "smtp": {
        "enabled": False,
        "host": "smtp.gmail.com",
        "port": 587,
        "from_addr": "watter008@gmail.com",
        "to_addrs": ["watter008@gmail.com"],
    },
    "morning_digest": {
        "schedule_local_time": "07:00",
        "watchlist_source": "db",
    },
    "refinement": {
        "max_depth": 3,
        "classifier_llm": "quick_think_llm",
        "action_expires_hours": 24,
    },
    "action_handler": {
        "tick_interval_seconds": 5,
    },
    "dashboard": {
        "enabled": False,
        "port": 8501,
        "bind_address": "127.0.0.1",
    },
    "refinement_chain_budget": {
        "enabled": False,
        "max_usd_per_chain": 10.0,
    },
    "morning_digest_token_ceiling": {
        "enabled": False,
        "max_in_tokens": 500_000,
    },
}))
