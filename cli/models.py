from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel


class AnalystType(str, Enum):
    MARKET = "market"
    # Wire value stays "social" for saved-config and string-keyed-caller
    # back-compat; the user-facing label is "Sentiment Analyst".
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
    INDIA_MARKET = "india_market"
    INDIA_FUNDAMENTALS = "india_fundamentals"
    INDIA_NEWS_FILINGS = "india_news_filings"
    INDIA_MACRO_POLICY = "india_macro_policy"
    INDIA_FLOWS = "india_flows"
    INDIA_SENTIMENT = "india_sentiment"
    INDIA_COMPLIANCE = "india_compliance"


class AssetType(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"
