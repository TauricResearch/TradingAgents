"""Vietnam stock market constants and configuration."""

MARKET_CODE = "VN"
MARKET_NAME = "Vietnam"
CURRENCY = "VND"
TIMEZONE = "Asia/Ho_Chi_Minh"  # UTC+7
TRADING_HOURS = "9:00-11:30, 13:00-15:00"
EXCHANGES = ["HOSE", "HNX", "UPCOM"]
PRICE_BANDS = {"HOSE": 7, "HNX": 10, "UPCOM": 15}  # percent
SETTLEMENT = "T+2"
DEFAULT_SOURCE = "VCI"  # Options: "VCI", "TCBS", "SSI"

# VnExpress RSS feed URLs (primary news source)
VNEXPRESS_RSS_URLS = [
    "https://vnexpress.net/rss/kinh-doanh.rss",
]

MARKET_CONTEXT = (
    "Vietnam (VN) market context: "
    "Exchanges: HOSE (Ho Chi Minh), HNX (Hanoi), UPCOM. "
    f"Trading hours: {TRADING_HOURS} (UTC+7). "
    "Price band limits: HOSE +/-7%, HNX +/-10%, UPCOM +/-15%. "
    f"Settlement: {SETTLEMENT}. "
    "Currency: VND. "
    "Key considerations: Foreign ownership limits apply to many stocks, "
    "SBV (State Bank of Vietnam) monetary policy impacts market sentiment, "
    "VND/USD exchange rate trends are important for foreign investors, "
    "VN30 index tracks the 30 largest HOSE-listed companies."
)
