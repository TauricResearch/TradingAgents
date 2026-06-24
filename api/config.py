import os
import datetime

DB_PATH = os.getenv(
    "TRADINGAGENTS_SIGNALS_DB_PATH",
    os.path.expanduser("~/.tradingagents/db/signals.db"),
)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
JWT_SECRET = os.getenv("PULSE_JWT_SECRET", os.getenv("JWT_SECRET", "pulse-secret-key"))
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "https://staging-backend.pulsenow.io")
FREE_TIER_QUOTA_LIMIT = int(os.getenv("FREE_TIER_QUOTA_LIMIT", "3"))
START_TIME = datetime.datetime.now()

# ponytail: local-only bypass — requires APP_ENV=development or service refuses to start
DEV_BYPASS_AUTH = os.getenv("DEV_BYPASS_AUTH", "").lower()
if DEV_BYPASS_AUTH and os.getenv("APP_ENV", "production") != "development":
    raise RuntimeError(
        "DEV_BYPASS_AUTH is set but APP_ENV != 'development' — refusing to start"
    )

TICKER_NAMES: dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "AVAX": "Avalanche",
    "LINK": "Chainlink",
    "ARB": "Arbitrum",
    "DOGE": "Dogecoin",
    "NVDA": "NVIDIA Corp",
    "TSLA": "Tesla Inc",
    "AMD": "AMD Corp",
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Corp",
}

GLOBAL_TICKERS: list[tuple] = [
    ("BTC", "crypto"),
    ("ETH", "crypto"),
    ("SOL", "crypto"),
    ("AVAX", "crypto"),
    ("LINK", "crypto"),
    ("ARB", "crypto"),
    ("DOGE", "crypto"),
    ("NVDA", "stocks"),
    ("TSLA", "stocks"),
    ("AMD", "stocks"),
    ("AAPL", "stocks"),
    ("MSFT", "stocks"),
]
