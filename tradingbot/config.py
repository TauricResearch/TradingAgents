"""
TradingBot runtime configuration.

Edit this file (or override via environment variables) to customise
your watchlist, position sizing, broker selection, and risk limits.
"""

import os

TRADINGBOT_CONFIG = {
    # ------------------------------------------------------------------ #
    # Broker                                                               #
    # ------------------------------------------------------------------ #
    # "alpaca" → AlpacaBroker (requires ALPACA_API_KEY / ALPACA_API_SECRET)
    # "mock"   → MockBroker   (no credentials needed, safe for testing)
    "broker": os.getenv("TRADINGBOT_BROKER", "mock"),

    # Set to False ONLY when you are ready for live money.
    "paper_trading": os.getenv("ALPACA_PAPER", "true").lower() != "false",

    "alpaca_api_key": os.getenv("ALPACA_API_KEY", ""),
    "alpaca_api_secret": os.getenv("ALPACA_API_SECRET", ""),

    # ------------------------------------------------------------------ #
    # Watchlist                                                            #
    # ------------------------------------------------------------------ #
    # Tickers the scheduler will analyse every trading day.
    "watchlist": os.getenv("TRADINGBOT_WATCHLIST", "AAPL,MSFT,NVDA,GOOGL,AMZN").split(","),

    # ------------------------------------------------------------------ #
    # Position sizing (passed to SignalMapper)                             #
    # ------------------------------------------------------------------ #
    # Fraction of available cash allocated on a full BUY signal.
    "full_position_pct": float(os.getenv("FULL_POSITION_PCT", "0.05")),

    # Fraction of available cash allocated on an OVERWEIGHT signal.
    "partial_position_pct": float(os.getenv("PARTIAL_POSITION_PCT", "0.03")),

    # Fraction of existing position sold on an UNDERWEIGHT signal.
    "partial_exit_pct": float(os.getenv("PARTIAL_EXIT_PCT", "0.50")),

    # ------------------------------------------------------------------ #
    # Risk Gate hard limits                                                #
    # ------------------------------------------------------------------ #
    # Maximum fraction of total portfolio in a single position.
    "max_single_position_pct": float(os.getenv("MAX_SINGLE_POSITION_PCT", "0.10")),

    # Maximum fraction of portfolio invested at any time (rest stays cash).
    "max_total_exposure_pct": float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "0.80")),

    # Circuit breaker: halt new buys if daily P&L drops below this fraction.
    # e.g. -0.02 means halt if down more than 2 % today.
    "daily_loss_limit_pct": float(os.getenv("DAILY_LOSS_LIMIT_PCT", "-0.02")),

    # Minimum cash reserve to always keep available (absolute dollars).
    "min_cash_reserve": float(os.getenv("MIN_CASH_RESERVE", "1000.0")),

    # ------------------------------------------------------------------ #
    # Scheduler                                                            #
    # ------------------------------------------------------------------ #
    # Timezone for all schedule times.
    "timezone": "America/New_York",

    # Time to run pre-market analysis (HH:MM, 24-hour).
    "pre_market_time": os.getenv("PRE_MARKET_TIME", "08:00"),

    # Time to submit orders after market open.
    "order_submission_time": os.getenv("ORDER_SUBMISSION_TIME", "09:35"),

    # Time to run post-market reflection.
    "post_market_time": os.getenv("POST_MARKET_TIME", "16:30"),

    # ------------------------------------------------------------------ #
    # Paths                                                                #
    # ------------------------------------------------------------------ #
    # SQLite database used by PortfolioManager.
    "db_path": os.getenv(
        "TRADINGBOT_DB_PATH",
        os.path.join(os.path.expanduser("~"), ".tradingagents", "tradingbot.db"),
    ),

    # Directory where TradingAgentsGraph saves full per-run JSON logs.
    # Must match TRADINGAGENTS_RESULTS_DIR (or the DEFAULT_CONFIG default).
    # The dashboard reads from here to show full agent reasoning per trade.
    "results_dir": os.getenv(
        "TRADINGAGENTS_RESULTS_DIR",
        os.path.join(os.path.expanduser("~"), ".tradingagents", "logs"),
    ),
}
