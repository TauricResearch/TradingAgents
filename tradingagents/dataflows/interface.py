import logging
import re
from datetime import date, datetime
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
from .provenance import DataProvenance, DataResult, utc_now
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

# Data whose provider exposes only a current snapshot. It is excluded when a
# historical cutoff is supplied instead of being mislabeled as historical fact.
LIVE_ONLY_METHODS = {
    "get_fundamentals",
    "get_insider_transactions",
    "get_prediction_markets",
}

_CUTOFF_ARG_INDEX = {
    "get_stock_data": 2,
    "get_indicators": 2,
    "get_fundamentals": 1,
    "get_balance_sheet": 2,
    "get_cashflow": 2,
    "get_income_statement": 2,
    "get_news": 2,
    "get_global_news": 0,
    "get_macro_indicators": 1,
}

_POINT_IN_TIME_STATUS = {
    "get_stock_data": "cutoff_enforced",
    "get_indicators": "cutoff_enforced",
    "get_news": "publication_time_filtered",
    "get_global_news": "publication_time_filtered",
    "get_macro_indicators": "observation_end_enforced",
    "get_balance_sheet": "period_end_cutoff_requested_availability_unverified",
    "get_cashflow": "period_end_cutoff_requested_availability_unverified",
    "get_income_statement": "period_end_cutoff_requested_availability_unverified",
    "get_fundamentals": "live_snapshot_only",
    "get_insider_transactions": "live_snapshot_only",
    "get_prediction_markets": "live_snapshot_only",
}

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization|secret)([=:]\s*)[^\s&,]+"
)
_EXPLICIT_UNAVAILABLE_PREFIXES = (
    "error retrieving",
    "data_unavailable:",
    "no_data_available:",
    "polymarket data is currently unavailable",
)

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

def _safe_error_text(exc: Exception) -> str:
    """Keep useful diagnostics while redacting common credential-shaped values."""
    return _SECRET_RE.sub(r"\1\2[REDACTED]", str(exc))


def _analysis_cutoff(
    method: str,
    args: tuple,
    explicit: str | None,
    kwargs: dict,
) -> str | None:
    if explicit:
        return str(explicit)
    if method in {"get_stock_data", "get_news"} and kwargs.get("end_date"):
        return str(kwargs["end_date"])
    if kwargs.get("curr_date"):
        return str(kwargs["curr_date"])
    index = _CUTOFF_ARG_INDEX.get(method)
    if index is not None and len(args) > index and args[index]:
        return str(args[index])
    return None


def _historical_cutoff(cutoff: str | None) -> bool:
    if not cutoff:
        return False
    try:
        return datetime.strptime(cutoff[:10], "%Y-%m-%d").date() < date.today()
    except (TypeError, ValueError):
        return False


def _quality_for_method(method: str) -> str:
    point_in_time = _POINT_IN_TIME_STATUS.get(method, "unknown")
    if point_in_time == "period_end_cutoff_requested_availability_unverified":
        return "limited"
    if point_in_time == "unknown":
        return "unknown"
    return "high"


def _explicitly_unavailable(content: Any) -> bool:
    if content is None:
        return True
    if not isinstance(content, str):
        return False
    normalized = content.strip().lower()
    return not normalized or normalized.startswith(_EXPLICIT_UNAVAILABLE_PREFIXES)


def _result(
    *,
    method: str,
    category: str,
    content,
    source: str | None,
    status: str,
    cutoff: str | None,
    attempts: list[dict[str, str]],
    quality: str | None = None,
) -> DataResult:
    fetched_at = utc_now()
    point_in_time = _POINT_IN_TIME_STATUS.get(method, "unknown")
    if point_in_time == "live_snapshot_only":
        data_as_of = fetched_at
    elif cutoff:
        data_as_of = f"on_or_before:{cutoff}"
    else:
        data_as_of = None
    return DataResult(
        content=content,
        provenance=DataProvenance(
            method=method,
            category=category,
            source=source,
            status=status,
            quality=quality or _quality_for_method(method),
            analysis_cutoff=cutoff,
            fetched_at=fetched_at,
            data_as_of=data_as_of,
            point_in_time=point_in_time,
            attempted_sources=attempts,
        ),
    )


def route_to_vendor_result(
    method: str,
    *args,
    analysis_cutoff: str | None = None,
    **kwargs,
) -> DataResult:
    """Route a call and return both payload and deterministic provenance."""
    category = get_category_for_method(method)
    cutoff = _analysis_cutoff(method, args, analysis_cutoff, kwargs)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available_vendors = list(VENDOR_METHODS[method].keys())

    # The configured vendor list IS the chain: we do NOT silently fall back to
    # vendors the user did not choose (#988/#289) — that returned data from an
    # unexpected source and caused cross-vendor inconsistencies. For multi-vendor
    # fallback, list them in order, e.g. data_vendors="yfinance,alpha_vantage".
    # The "default" sentinel (no explicit config) uses all available vendors.
    explicit = [v for v in primary_vendors if v and v != "default"]
    if explicit:
        vendor_chain = [v for v in explicit if v in VENDOR_METHODS[method]]
        if not vendor_chain:
            raise ValueError(
                f"Configured vendor(s) {explicit} not available for '{method}'. "
                f"Available: {all_available_vendors}."
            )
    else:
        vendor_chain = all_available_vendors

    if method in LIVE_ONLY_METHODS and _historical_cutoff(cutoff):
        content = (
            f"DATA_UNAVAILABLE: {method} exposes a live snapshot only and was excluded "
            f"from historical analysis with cutoff {cutoff}. Do not treat current values "
            "as facts known at that historical date."
        )
        return _result(
            method=method,
            category=category,
            content=content,
            source=None,
            status="unavailable",
            cutoff=cutoff,
            attempts=[],
            quality="unavailable",
        )

    last_no_data: NoMarketDataError | None = None
    first_error: Exception | None = None
    attempts: list[dict[str, str]] = []
    for vendor in vendor_chain:
        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            content = impl_func(*args, **kwargs)
            if _explicitly_unavailable(content):
                attempts.append({"source": vendor, "status": "unavailable"})
                detail = "vendor returned an explicit unavailable payload"
                if category in OPTIONAL_CATEGORIES:
                    if first_error is None:
                        first_error = RuntimeError(detail)
                else:
                    symbol = str(args[0]) if args else method
                    last_no_data = NoMarketDataError(symbol, symbol, detail)
                continue
            attempts.append({"source": vendor, "status": "available"})
            return _result(
                method=method,
                category=category,
                content=content,
                source=vendor,
                status="available",
                cutoff=cutoff,
                attempts=attempts,
            )
        except VendorRateLimitError:
            logger.warning("Vendor %r rate-limited for %s; trying next vendor.", vendor, method)
            attempts.append({"source": vendor, "status": "rate_limited"})
            continue
        except VendorNotConfiguredError as e:
            logger.warning("Vendor %r not configured for %s; trying next vendor.", vendor, method)
            attempts.append({"source": vendor, "status": "not_configured"})
            if first_error is None:
                first_error = e  # Surface it if no other vendor can serve the call.
            continue
        except NoMarketDataError as e:
            attempts.append({"source": vendor, "status": "no_data"})
            last_no_data = e  # No data here; another configured vendor may have it
            continue
        except Exception as e:
            # Don't let one vendor's failure crash the call when another can
            # serve it, but never swallow silently: a broken primary must be
            # visible in the logs (#989), not hidden behind a fallback's verdict.
            logger.warning("Vendor %r failed for %s: %s", vendor, method, _safe_error_text(e))
            attempts.append({"source": vendor, "status": "error"})
            if first_error is None:
                first_error = e
            continue

    # If any vendor reported "no data", the symbol is genuinely unavailable.
    # Return one explicit, instructive sentinel rather than a vendor-specific
    # empty string, so the agent reports "unavailable" instead of inventing a
    # value. This takes precedence over incidental fallback errors.
    if last_no_data is not None:
        if first_error is not None:
            # A vendor also hit a real error; surface it in logs so the no-data
            # verdict can't hide a broken primary (network/auth/etc.).
            logger.warning(
                "Returning NO_DATA for %s, but a vendor errored earlier: %s",
                method, _safe_error_text(first_error),
            )
        sym = last_no_data.symbol
        canonical = last_no_data.canonical
        resolved = "" if canonical == sym else f" (resolved to '{canonical}')"
        # Surface the typed error's detail (e.g. "latest row is 2025-06-11 ...
        # stale") so the agent sees the specific reason — invalid symbol, no
        # coverage, or stale data — not just a generic "unavailable".
        reason = f" ({last_no_data.detail})" if last_no_data.detail else ""
        content = (
            f"NO_DATA_AVAILABLE: No usable market data for '{sym}'{resolved} from "
            f"any configured vendor{reason}. The symbol may be invalid, delisted, "
            f"not covered, or the vendor returned stale data. Do not estimate or "
            f"fabricate values — report that data is unavailable for this symbol."
        )
        return _result(
            method=method,
            category=category,
            content=content,
            source=None,
            status="no_data",
            cutoff=cutoff,
            attempts=attempts,
            quality="unavailable",
        )

    # No vendor returned data and none reported clean "no data" — surface the
    # first real error (e.g. the primary vendor's network failure). Optional
    # enrichment categories degrade to a sentinel instead, so flavour data can't
    # abort the run.
    if first_error is not None:
        if category in OPTIONAL_CATEGORIES:
            logger.warning(
                "Optional %s unavailable for %s: %s",
                category,
                method,
                _safe_error_text(first_error),
            )
            safe_error = _safe_error_text(first_error)
            content = (
                f"DATA_UNAVAILABLE: optional {category} could not be retrieved "
                f"({safe_error}). Proceed without it; do not fabricate values."
            )
            return _result(
                method=method,
                category=category,
                content=content,
                source=None,
                status="unavailable",
                cutoff=cutoff,
                attempts=attempts,
                quality="unavailable",
            )
        raise first_error

    raise RuntimeError(f"No available vendor for '{method}'")


def route_to_vendor(method: str, *args, **kwargs):
    """Backwards-compatible router returning the provider payload only."""
    return route_to_vendor_result(method, *args, **kwargs).content


def route_to_vendor_with_provenance(method: str, *args, **kwargs) -> str:
    """Route a call and render its provenance contract for analyst tools."""
    return route_to_vendor_result(method, *args, **kwargs).render()
