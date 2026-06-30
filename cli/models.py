from enum import Enum


class AnalystType(str, Enum):
    MARKET = "market"
    # Wire value stays "social" for saved-config and string-keyed-caller
    # back-compat; the user-facing label is "Sentiment Analyst".
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
    TECHNICAL = "technical"
    QUANT = "quant"
    OPTIONS = "options"
    ALTERNATIVE_DATA = "alternative_data"


class AssetType(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"
