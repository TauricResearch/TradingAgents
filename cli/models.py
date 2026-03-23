from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel


class AnalysisMode(str, Enum):
    STOCK = "stock"
    POLYMARKET = "polymarket"


class AnalystType(str, Enum):
    MARKET = "market"
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"


class PMAnalystType(str, Enum):
    EVENT = "event"
    ODDS = "odds"
    INFORMATION = "information"
    SENTIMENT = "sentiment"
