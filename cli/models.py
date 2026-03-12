from enum import Enum


class AnalystType(str, Enum):
    MARKET = "market"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
