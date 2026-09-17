"""Optional Investboard vendor.

Investboard (https://investboard.de) serves the core data categories from the
user's own account: price history, fundamentals, statements, company news and
insider transactions for the instruments they hold, watch or registered, with
nothing dated after the analysis date. The vendor itself lives in the companion
package ``tradingagents-investboard``, which also handles sign-in (OAuth in the
browser, no API key) and posts the finished analysis back to the account.

This module only registers that vendor when the package is installed. Without
it, nothing changes. Select it like any other vendor::

    config["data_vendors"]["core_stock_apis"] = "investboard"
"""

from __future__ import annotations


def register() -> bool:
    """Register the ``investboard`` vendor if its package is installed."""
    try:
        import tradingagents_investboard.vendor  # noqa: F401  (registers on import)
    except ImportError:
        return False
    return True
