import logging
import time
from typing import Any

from .alpha_vantage import (
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_global_news as get_alpha_vantage_global_news,
    get_income_statement as get_alpha_vantage_income_statement,
    get_indicator as get_alpha_vantage_indicator,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_stock as get_alpha_vantage_stock,
)
from .config import get_config
from .errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorRateLimitError,
)
from .fred import get_macro_data as get_fred_macro_data
from .polymarket import get_prediction_markets as get_polymarket_prediction_markets
from .y_finance import (
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_fundamentals as get_yfinance_fundamentals,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
    get_stock_stats_indicators_window,
    get_YFin_data_online,
)
from .yfinance_news import get_global_news_yfinance, get_news_yfinance

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Tracks vendor failures and temporarily skips repeatedly failing vendors.

    After *failure_threshold* consecutive failures, the circuit "opens" and
    the vendor is skipped for *reset_timeout* seconds. After the timeout, one
    probe request is allowed (half-open state); if it succeeds the circuit
    resets, if it fails the circuit re-opens.

    Only transient errors (rate limits, network failures) should trip the
    breaker — permanent conditions like misconfiguration or missing data do
    not affect vendor health.
    """

    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 300.0):
        self._threshold = failure_threshold
        self._timeout = reset_timeout
        self._failures: dict[str, int] = {}
        self._open_since: dict[str, float] = {}

    def is_open(self, vendor: str) -> bool:
        """Return True if *vendor* is currently circuit-broken (skipped)."""
        failures = self._failures.get(vendor, 0)
        if failures < self._threshold:
            return False
        elapsed = time.monotonic() - self._open_since.get(vendor, 0.0)
        if elapsed >= self._timeout:
            # Half-open: allow one probe request through
            return False
        return True

    def record_failure(self, vendor: str) -> None:
        """Record a transient failure and open the circuit if threshold reached."""
        self._failures[vendor] = self._failures.get(vendor, 0) + 1
        if self._failures[vendor] >= self._threshold:
            self._open_since.setdefault(vendor, time.monotonic())

    def record_success(self, vendor: str) -> None:
        """Reset the failure count after a successful request."""
        self._failures.pop(vendor, None)
        self._open_since.pop(vendor, None)

    def reset(self, vendor: str | None = None) -> None:
        """Manually reset the breaker for *vendor*, or all vendors if omitted."""
        if vendor is None:
            self._failures.clear()
            self._open_since.clear()
        else:
            self._failures.pop(vendor, None)
            self._open_since.pop(vendor, None)


# Module-level circuit breaker shared across all route_to_vendor calls.
# Reset between tests via reset_circuit_breaker().
_circuit_breaker: CircuitBreaker = CircuitBreaker()


def reset_circuit_breaker() -> None:
    """Reset the circuit breaker (primarily for test isolation)."""
    global _circuit_breaker
    _circuit_breaker = CircuitBreaker()

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    },
    "macro_data": {
        "description": "Macroeconomic indicators (rates, inflation, labor, growth)",
        "tools": [
            "get_macro_indicators",
        ]
    },
    "prediction_markets": {
        "description": "Market-implied probabilities for forward-looking events",
        "tools": [
            "get_prediction_markets",
        ]
    }
}

VENDOR_LIST = [
    "yfinance",
    "fred",
    "polymarket",
    "alpha_vantage",
]

# Optional enrichment categories. These add macro/event context to the news
# analyst but are not core to a decision, so a vendor failure here degrades to a
# sentinel instead of aborting the run (a bad LLM-supplied indicator, a missing
# key, or a network blip should not crash an analysis over flavour data). Core
# categories (prices, fundamentals, news) still raise so a broken primary is loud.
OPTIONAL_CATEGORIES = {"macro_data", "prediction_markets"}

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # macro_data
    "get_macro_indicators": {
        "fred": get_fred_macro_data,
    },
    # prediction_markets
    "get_prediction_markets": {
        "polymarket": get_polymarket_prediction_markets,
    },
}

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def _resolve_vendor_chain(method: str, category: str) -> list[str]:
    """Resolve the ordered vendor chain for *method* from the user's config.

    The configured vendor list IS the chain: we do NOT silently fall back to
    vendors the user did not choose (#988/#289).  The "default" sentinel (no
    explicit config) uses all available vendors.
    """
    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(",")]
    all_available_vendors = list(VENDOR_METHODS[method].keys())

    explicit = [v for v in primary_vendors if v and v != "default"]
    if explicit:
        vendor_chain = [v for v in explicit if v in VENDOR_METHODS[method]]
        if not vendor_chain:
            raise ValueError(
                f"Configured vendor(s) {explicit} not available for '{method}'. "
                f"Available: {all_available_vendors}."
            )
        return vendor_chain
    return all_available_vendors


def _build_no_data_message(
    last_no_data: NoMarketDataError,
    first_error: Exception | None,
    method: str,
) -> str:
    """Build the ``NO_DATA_AVAILABLE`` sentinel when no vendor could return data."""
    if first_error is not None:
        logger.warning(
            "Returning NO_DATA for %s, but a vendor errored earlier: %s",
            method, first_error,
        )
    sym = last_no_data.symbol
    canonical = last_no_data.canonical
    resolved = "" if canonical == sym else f" (resolved to '{canonical}')"
    reason = f" ({last_no_data.detail})" if last_no_data.detail else ""
    return (
        f"NO_DATA_AVAILABLE: No usable market data for '{sym}'{resolved} from "
        f"any configured vendor{reason}. The symbol may be invalid, delisted, "
        f"not covered, or the vendor returned stale data. Do not estimate or "
        f"fabricate values — report that data is unavailable for this symbol."
    )


def _build_unavailable_message(
    first_error: Exception,
    category: str,
    method: str,
) -> str:
    """Build the ``DATA_UNAVAILABLE`` sentinel for optional enrichment categories."""
    logger.warning("Optional %s unavailable for %s: %s", category, method, first_error)
    return (
        f"DATA_UNAVAILABLE: optional {category} could not be retrieved "
        f"({first_error}). Proceed without it; do not fabricate values."
    )


def _try_vendor(
    vendor: str,
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Call the vendor implementation, returning data or raising on failure."""
    vendor_impl = VENDOR_METHODS[method][vendor]
    impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl
    return impl_func(*args, **kwargs)


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_chain = _resolve_vendor_chain(method, category)

    last_no_data: NoMarketDataError | None = None
    first_error: Exception | None = None

    for vendor in vendor_chain:
        if _circuit_breaker.is_open(vendor):
            logger.info("Circuit-breaker open for %r; skipping.", vendor)
            continue

        try:
            result = _try_vendor(vendor, method, args, kwargs)
            _circuit_breaker.record_success(vendor)
            return result
        except VendorRateLimitError:
            logger.warning("Vendor %r rate-limited for %s; trying next.", vendor, method)
            _circuit_breaker.record_failure(vendor)
            continue
        except VendorNotConfiguredError as e:
            logger.warning("Vendor %r not configured for %s; trying next.", vendor, method)
            if first_error is None:
                first_error = e
            continue
        except NoMarketDataError as e:
            last_no_data = e
            continue
        except Exception as e:
            logger.warning("Vendor %r failed for %s: %s", vendor, method, e)
            _circuit_breaker.record_failure(vendor)
            if first_error is None:
                first_error = e
            continue

    # All vendors exhausted — surface the best diagnostic available.
    if last_no_data is not None:
        return _build_no_data_message(last_no_data, first_error, method)

    if first_error is not None:
        if category in OPTIONAL_CATEGORIES:
            return _build_unavailable_message(first_error, category, method)
        raise first_error

    raise RuntimeError(f"No available vendor for '{method}'")
