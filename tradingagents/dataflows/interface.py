from __future__ import annotations

from datetime import datetime
from typing import Any

from tradingagents.agents.utils.instrument_resolver import resolve_instrument

from .alpha_vantage import (
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_company_news_alpha_vantage,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_income_statement as get_alpha_vantage_income_statement,
    get_indicator as get_alpha_vantage_indicator,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_macro_news_alpha_vantage,
    get_stock as get_alpha_vantage_stock,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .config import get_config
from .ecos import get_macro_news_ecos
from .naver_news import get_company_news_naver, get_social_sentiment_naver
from .opendart import get_disclosures_opendart
from .vendor_exceptions import (
    VendorConfigurationError,
    VendorInputError,
    VendorMalformedResponseError,
    VendorTransientError,
)
from .y_finance import (
    get_YFin_data_online,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_fundamentals as get_yfinance_fundamentals,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
    get_stock_stats_indicators_window,
)
from .yfinance_news import (
    get_company_news_yfinance,
    get_macro_news_yfinance,
    get_social_sentiment_yfinance,
)


TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": ["get_stock_data"],
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": ["get_indicators"],
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
            "get_insider_transactions",
        ],
    },
    "news_data": {
        "description": "Company news feeds",
        "tools": ["get_news", "get_company_news"],
    },
    "macro_data": {
        "description": "Macro and market context feeds",
        "tools": ["get_global_news", "get_macro_news"],
    },
    "disclosure_data": {
        "description": "Corporate disclosures and filings",
        "tools": ["get_disclosures"],
    },
    "social_data": {
        "description": "Social and public narrative sentiment",
        "tools": ["get_social_sentiment"],
    },
}

VENDOR_LIST = [
    "alpha_vantage",
    "yfinance",
    "naver",
    "opendart",
    "ecos",
]

VENDOR_METHODS = {
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
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
    "get_news": {
        "alpha_vantage": get_company_news_alpha_vantage,
        "yfinance": get_company_news_yfinance,
        "naver": get_company_news_naver,
    },
    "get_company_news": {
        "alpha_vantage": get_company_news_alpha_vantage,
        "yfinance": get_company_news_yfinance,
        "naver": get_company_news_naver,
    },
    "get_global_news": {
        "alpha_vantage": get_macro_news_alpha_vantage,
        "yfinance": get_macro_news_yfinance,
        "ecos": get_macro_news_ecos,
    },
    "get_macro_news": {
        "alpha_vantage": get_macro_news_alpha_vantage,
        "yfinance": get_macro_news_yfinance,
        "ecos": get_macro_news_ecos,
    },
    "get_disclosures": {
        "opendart": get_disclosures_opendart,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    "get_social_sentiment": {
        "naver": get_social_sentiment_naver,
        "yfinance": get_social_sentiment_yfinance,
    },
}

_SEMANTIC_EMPTY_MARKERS = (
    "no news found",
    "no global news found",
    "no disclosures found",
    "no insider transactions data found",
    "no data found",
    "no fundamentals data found",
    "provider unavailable",
    "no social provider",
    "no social sentiment",
)


def get_category_for_method(method: str) -> str:
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str | None = None) -> str:
    config = get_config()
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]
    return config.get("data_vendors", {}).get(category, "yfinance")


def _normalize_vendor_chain(method: str, vendor_config: str) -> list[str]:
    configured = [vendor.strip() for vendor in (vendor_config or "").split(",") if vendor.strip()]
    if not configured:
        raise ValueError(f"No vendors configured for '{method}'.")

    available = VENDOR_METHODS.get(method, {})
    invalid = [vendor for vendor in configured if vendor not in available]
    if invalid:
        invalid_list = ", ".join(sorted(invalid))
        raise ValueError(f"Unsupported vendors for '{method}': {invalid_list}.")

    chain = configured.copy()
    for vendor in available:
        if vendor not in chain:
            chain.append(vendor)
    return chain


def _prioritize_market_specific_vendors(method: str, vendor_chain: list[str], args: tuple[Any, ...], kwargs: dict[str, Any]) -> list[str]:
    reordered = vendor_chain[:]

    def promote(vendor_name: str) -> None:
        if vendor_name in reordered:
            reordered.remove(vendor_name)
            reordered.insert(0, vendor_name)

    try:
        if method in {"get_news", "get_company_news", "get_social_sentiment", "get_disclosures"}:
            symbol = kwargs.get("symbol") or kwargs.get("ticker") or (args[0] if args else None)
            if isinstance(symbol, str):
                profile = resolve_instrument(symbol)
                if profile.country == "KR":
                    if method in {"get_news", "get_company_news", "get_social_sentiment"}:
                        promote("naver")
                    if method == "get_disclosures":
                        promote("opendart")
        if method in {"get_global_news", "get_macro_news"}:
            region = kwargs.get("region") or (args[3] if len(args) > 3 else None)
            if isinstance(region, str) and region.upper() == "KR":
                promote("ecos")
    except Exception:
        return reordered

    return reordered


def _validate_date(value: str, field_name: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise VendorInputError(f"Field '{field_name}' must be in YYYY-MM-DD format.") from exc


def _validate_input_for_method(method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    def arg(index: int, name: str) -> Any:
        if name in kwargs:
            return kwargs[name]
        return args[index] if len(args) > index else None

    if method in {
        "get_stock_data",
        "get_indicators",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
        "get_news",
        "get_company_news",
        "get_disclosures",
        "get_insider_transactions",
        "get_social_sentiment",
    }:
        symbol = arg(0, "symbol") or arg(0, "ticker")
        if not isinstance(symbol, str) or not symbol.strip():
            raise VendorInputError("A non-empty ticker or symbol is required.")

    if method in {"get_stock_data", "get_news", "get_company_news", "get_disclosures", "get_social_sentiment"}:
        _validate_date(str(arg(1, "start_date")), "start_date")
        _validate_date(str(arg(2, "end_date")), "end_date")

    if method in {"get_global_news", "get_macro_news"}:
        _validate_date(str(arg(0, "curr_date")), "curr_date")
        look_back_days = arg(1, "look_back_days")
        limit = arg(2, "limit")
        if look_back_days is not None and int(look_back_days) < 0:
            raise VendorInputError("'look_back_days' must be non-negative.")
        if limit is not None and int(limit) <= 0:
            raise VendorInputError("'limit' must be positive.")


def should_fallback(result_or_exc: Any, method: str | None = None) -> bool:
    config = get_config()
    empty_result_fallback = bool(config.get("empty_result_fallback", True))

    if isinstance(result_or_exc, VendorInputError):
        return False

    if isinstance(
        result_or_exc,
        (
            AlphaVantageRateLimitError,
            VendorConfigurationError,
            VendorTransientError,
            VendorMalformedResponseError,
        ),
    ):
        return True

    if isinstance(result_or_exc, Exception):
        return True

    if not empty_result_fallback:
        return False

    if result_or_exc is None:
        return True

    if isinstance(result_or_exc, (list, tuple, dict, set)) and len(result_or_exc) == 0:
        return True

    if isinstance(result_or_exc, str):
        normalized = result_or_exc.strip().lower()
        if not normalized:
            return True
        if normalized.startswith("error"):
            return True
        if any(marker in normalized for marker in _SEMANTIC_EMPTY_MARKERS):
            return True

    return False


def route_to_vendor(method: str, *args, **kwargs):
    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    _validate_input_for_method(method, args, kwargs)

    category = get_category_for_method(method)
    vendor_chain = _normalize_vendor_chain(method, get_vendor(category, method))
    vendor_chain = _prioritize_market_specific_vendors(method, vendor_chain, args, kwargs)

    fallback_notes: list[str] = []
    last_result = None
    last_exception: Exception | None = None

    for vendor in vendor_chain:
        vendor_impl = VENDOR_METHODS[method].get(vendor)
        if vendor_impl is None:
            continue

        try:
            result = vendor_impl(*args, **kwargs)
            if should_fallback(result, method):
                last_result = result
                fallback_notes.append(f"{vendor}: empty or unusable result")
                continue
            return result
        except VendorInputError:
            raise
        except Exception as exc:
            if should_fallback(exc, method):
                last_exception = exc
                fallback_notes.append(f"{vendor}: {exc}")
                continue
            raise

    if last_result is not None:
        return last_result

    if last_exception is not None:
        note = " | ".join(fallback_notes)
        raise RuntimeError(f"No available vendor for '{method}'. Fallback attempts: {note}") from last_exception

    raise RuntimeError(f"No available vendor for '{method}'.")
