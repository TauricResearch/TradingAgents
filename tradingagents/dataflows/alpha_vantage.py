# Import functions from specialized modules
from .alpha_vantage_stock import get_stock
from .alpha_vantage_indicator import get_indicator
from .alpha_vantage_fundamentals import get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement
from .alpha_vantage_news import get_news, get_global_news, get_insider_transactions

# `dataflows/interface.py` consumes this shim via
# `from .alpha_vantage import get_X as get_alpha_vantage_X`. Declaring
# `__all__` prevents lint/type tools from treating these re-exports as
# unused imports and auto-deleting them, which would silently break the
# data-vendor routing layer at import time.
__all__ = [
    "get_balance_sheet",
    "get_cashflow",
    "get_fundamentals",
    "get_global_news",
    "get_income_statement",
    "get_indicator",
    "get_insider_transactions",
    "get_news",
    "get_stock",
]