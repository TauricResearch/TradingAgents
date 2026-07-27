import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
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
from .china_capabilities import (
    get_a_share_interactive_answers,
    get_a_share_interactive_questions,
    get_cls_telegraph,
    search_a_share_iwencai,
)
from .china_capital_flow import (
    get_a_share_insider_trades,
    get_a_share_northbound_flow,
    get_a_share_northbound_holdings,
)
from .china_data import (
    ChinaDataUnavailableError,
    get_balance_sheet_akshare,
    get_balance_sheet_tushare,
    get_cashflow_akshare,
    get_cashflow_tushare,
    get_fundamentals_akshare,
    get_fundamentals_tushare,
    get_income_statement_akshare,
    get_income_statement_tushare,
    get_stock_akshare,
    get_stock_tushare,
)
from .china_macro import get_china_macro_indicators
from .china_specialty import (
    get_a_share_exchange_announcements,
    get_a_share_official_news,
)
from .china_specialty_em import (
    get_a_share_break_board_pool,
    get_a_share_bulk_trades_em,
    get_a_share_concept_blocks,
    get_a_share_daily_dragon_tiger,
    get_a_share_dragon_tiger_em,
    get_a_share_dragon_tiger_official,
    get_a_share_eps_forecast,
    get_a_share_industry_ranking,
    get_a_share_limit_down_pool,
    get_a_share_limit_up_ladder_em,
    get_a_share_lockup_releases_em,
    get_a_share_prev_limit_up_pool,
    get_a_share_research_reports,
    get_a_share_shareholder_counts_em,
)
from .eastmoney import (
    get_a_share_capital_flow,
    get_a_share_capital_flow_sina,
    get_a_share_margin_financing,
)
from .fred import get_macro_data as get_fred_macro_data
from .mootdx_provider import get_stock_mootdx
from .option_provider import get_a_share_option_greeks, get_a_share_option_tquote
from .sentiment_provider import get_a_share_hot_concept, get_a_share_hot_list
from .symbol_utils import NoMarketDataError
from .tavily_news import (
    get_global_news_tavily,
    get_news_tavily,
)
from .tencent_provider import get_a_share_valuation
from .ticker_utils import (
    is_a_share_ticker,
)

# Import from vendor-specific modules
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

try:
    from curl_cffi.requests.exceptions import RequestException as CurlCffiRequestException
except Exception:  # pragma: no cover - curl_cffi is an indirect yfinance dependency
    CurlCffiRequestException = ()

# Configuration and routing logic
from tradingagents.observability.context import current_observation_context
from tradingagents.observability.provenance import (
    CacheOrigin,
    DataRequestObservation,
    begin_data_request,
)

from .china_supplemental import (  # noqa: F401  - re-exported for callers that import from interface
    _format_incomplete_primary_result,
    _format_supplemental_result,
    _is_china_supplemental_vendor,
    _next_china_supplemental_vendor,
)
from .config import get_config
from .errors import (  # noqa: F401  - DataUnavailableError re-exported for callers
    DataSourceUnavailableError,
    DataUnavailableError,
    VendorError,
    VendorRateLimitError,
)
from .health import (  # noqa: F401  - _vendor_health/set/clear re-exported for callers
    RATE_LIMIT_COOLDOWN_SECONDS,
    TRANSIENT_FAILURE_COOLDOWN_SECONDS,
    VendorHealthRegistry,
    _vendor_health,
    clear_vendor_health,
    set_vendor_health_registry,
)
from .news_curator import (  # noqa: F401  - re-exported for callers that import from interface
    _company_short_form,
    _dedupe_news_items,
    _extract_json_news_items,
    _extract_markdown_news_items,
    _extract_news_items,
    _filter_stale_items,
    _format_curated_news,
    _is_empty_news_result,
    _is_error_news_result,
    _is_relevant_news_item,
    _mark_news_relevance,
    _news_dedupe_key,
    _parse_date_best_effort,
    _summarize_empty_news_result,
    _summarize_error_news_result,
    _summarize_news_result,
    _summarize_vendor_error_for_news,
)
from .progress import (  # noqa: F401  - re-exported for callers that import from interface
    _emit_data_progress,
    _emit_supplement_progress,
    _format_progress_context,
    _sanitize_progress_text,
)
from .vendor_errors import (  # noqa: F401  - re-exported for callers that import from interface
    _cooldown_for_exception,
    _format_vendor_unavailable_message,
    _http_status_code,
    _is_missing_required_data_result,
    _is_recoverable_vendor_error,
    _is_transient_vendor_error,
    _record_vendor_failure,
    _record_vendor_success,
    _should_halt_on_missing_data,
    _summarize_vendor_error,
)
from .yfinance_incompleteness import (  # noqa: F401  - re-exported for callers that import from interface
    _expected_weekday_count,
    _parse_csv_from_report,
    _should_supplement_yfinance_result,
    _summarize_data_result,
    _summarize_yfinance_fundamentals_incompleteness,
    _summarize_yfinance_incompleteness,
    _summarize_yfinance_statement_incompleteness,
    _summarize_yfinance_stock_incompleteness,
)

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {"description": "OHLCV stock price data", "tools": ["get_stock_data"]},
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": ["get_indicators"],
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": ["get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement"],
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ],
    },
    "macro_data": {
        "description": "Macroeconomic indicators (rates, inflation, labor, growth)",
        "tools": [
            "get_macro_indicators",
        ],
    },
    "a_share_market_data": {
        "description": "A-share supplemental capital-flow, northbound, insider, margin-financing, and announcements",
        "tools": [
            "get_a_share_capital_flow",
            "get_a_share_northbound_flow",
            "get_a_share_northbound_holdings",
            "get_a_share_insider_trades",
            "get_a_share_margin_financing",
            "get_a_share_exchange_announcements",
        ],
    },
    "a_share_valuation": {
        "description": "A-share realtime valuation (PE/PB/market-cap/turnover/price-limits) via Tencent",
        "tools": ["get_a_share_valuation"],
    },
    "a_share_research": {
        "description": "A-share research reports and consensus EPS forecast",
        "tools": ["get_a_share_research_reports", "get_a_share_eps_forecast"],
    },
    "a_share_options": {
        "description": "A-share ETF option T-quotes and Greeks/IV",
        "tools": ["get_a_share_option_tquote", "get_a_share_option_greeks"],
    },
    "a_share_sentiment": {
        "description": "A-share market hot list and hot-concept hits",
        "tools": ["get_a_share_hot_list", "get_a_share_hot_concept"],
    },
    "china_macro_data": {
        "description": "Optional China macro and economic-cycle source series",
        "tools": ["get_china_macro_indicators"],
    },
    "a_share_specialty_data": {
        "description": "A-share public specialty datasets (bulk trades, holders, lockups, dragon-tiger, limit-up, and Interactive Q&A)",
        "tools": [
            "get_a_share_bulk_trades",
            "get_a_share_shareholder_counts",
            "get_a_share_lockup_releases",
            "get_a_share_dragon_tiger",
            "get_a_share_limit_up_ladder",
            "get_a_share_daily_dragon_tiger",
            "get_a_share_industry_ranking",
            "get_a_share_concept_blocks",
            "get_a_share_break_board_pool",
            "get_a_share_limit_down_pool",
            "get_a_share_prev_limit_up_pool",
            "get_a_share_interactive_questions",
            "get_a_share_interactive_answers",
        ],
    },
    "a_share_query_data": {
        "description": "Optional iWenCai natural-language query capability",
        "tools": ["search_a_share_iwencai"],
    },
    "a_share_telegraph": {
        "description": "CLS telegraph capability; unavailable unless a reviewed signer is configured",
        "tools": ["get_cls_telegraph"],
    },
}

VENDOR_LIST = [
    "mootdx",
    "tencent",
    "ths",
    "tushare",
    "akshare",
    "sina",
    "tavily",
    "yfinance",
    "fred",
    "alpha_vantage",
    "eastmoney",
    "china_exchange",
    "iwencai",
    "cls",
]

# Vendor market capability matrix.
# Each vendor lists the markets it can serve. A-share-only vendors are skipped
# for non-A-share tickers; global-only vendors are skipped for A-share tickers.
# Vendors serving both markets are never skipped by the market filter. Adding a
# vendor only needs an entry here, not a new branch in _should_skip_vendor_for_symbol.
VENDOR_MARKETS: dict[str, frozenset[str]] = {
    "mootdx": frozenset({"a_share"}),
    "tencent": frozenset({"a_share"}),
    "ths": frozenset({"a_share"}),
    "tushare": frozenset({"a_share"}),
    "akshare": frozenset({"a_share"}),
    "eastmoney": frozenset({"a_share"}),
    "china_exchange": frozenset({"a_share"}),
    "iwencai": frozenset({"a_share"}),
    "cls": frozenset({"a_share"}),
    "sina": frozenset({"a_share"}),
    "yfinance": frozenset({"global"}),
    "fred": frozenset({"global"}),
    "alpha_vantage": frozenset({"a_share", "global"}),
    "tavily": frozenset({"a_share", "global"}),
}

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "mootdx": get_stock_mootdx,
        "tushare": get_stock_tushare,
        "akshare": get_stock_akshare,
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
        "tushare": get_fundamentals_tushare,
        "akshare": get_fundamentals_akshare,
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "tushare": get_balance_sheet_tushare,
        "akshare": get_balance_sheet_akshare,
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "tushare": get_cashflow_tushare,
        "akshare": get_cashflow_akshare,
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "tushare": get_income_statement_tushare,
        "akshare": get_income_statement_akshare,
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "tavily": get_news_tavily,
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
        # A fallback-only adapter for public exchange announcements.  It is
        # appended only after ordinary news sources cannot return usable A
        # share news; see ``_news_official_fallback_vendors``.
        "china_exchange": get_a_share_official_news,
    },
    "get_global_news": {
        "tavily": get_global_news_tavily,
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
    "get_china_macro_indicators": {
        "akshare": get_china_macro_indicators,
    },
    # Optional, zero-key supplemental A-share capabilities.  They are kept
    # separate from OHLCV so a changed public endpoint cannot poison core
    # price/fundamental routing.
    "get_a_share_capital_flow": {
        "eastmoney": get_a_share_capital_flow,
        "sina": get_a_share_capital_flow_sina,
    },
    "get_a_share_northbound_flow": {"akshare": get_a_share_northbound_flow},
    "get_a_share_northbound_holdings": {"akshare": get_a_share_northbound_holdings},
    "get_a_share_insider_trades": {"akshare": get_a_share_insider_trades},
    "get_a_share_margin_financing": {
        "eastmoney": get_a_share_margin_financing,
    },
    "get_a_share_exchange_announcements": {
        # This adapter itself uses the relevant official exchange first and
        # explicitly-labelled keyless public fallback second.
        "china_exchange": get_a_share_exchange_announcements,
    },
    # Public specialty datasets delivered by AKShare.  These are deliberately
    # separate from core market data because they are optional supplements.
    "get_a_share_bulk_trades": {"eastmoney": get_a_share_bulk_trades_em},
    "get_a_share_shareholder_counts": {"eastmoney": get_a_share_shareholder_counts_em},
    "get_a_share_lockup_releases": {"eastmoney": get_a_share_lockup_releases_em},
    "get_a_share_dragon_tiger": {"eastmoney": get_a_share_dragon_tiger_em},
    "get_a_share_limit_up_ladder": {"eastmoney": get_a_share_limit_up_ladder_em},
    "get_a_share_daily_dragon_tiger": {
        "eastmoney": get_a_share_daily_dragon_tiger,
        "china_exchange": get_a_share_dragon_tiger_official,
    },
    "get_a_share_break_board_pool": {"eastmoney": get_a_share_break_board_pool},
    "get_a_share_valuation": {"tencent": get_a_share_valuation},
    "get_a_share_research_reports": {"eastmoney": get_a_share_research_reports},
    "get_a_share_eps_forecast": {"ths": get_a_share_eps_forecast},
    "get_a_share_industry_ranking": {"eastmoney": get_a_share_industry_ranking},
    "get_a_share_concept_blocks": {"eastmoney": get_a_share_concept_blocks},
    "get_a_share_option_tquote": {"sina": get_a_share_option_tquote},
    "get_a_share_option_greeks": {"sina": get_a_share_option_greeks},
    "get_a_share_hot_list": {"ths": get_a_share_hot_list},
    "get_a_share_hot_concept": {"eastmoney": get_a_share_hot_concept},
    "get_a_share_limit_down_pool": {"eastmoney": get_a_share_limit_down_pool},
    "get_a_share_prev_limit_up_pool": {"eastmoney": get_a_share_prev_limit_up_pool},
    "get_a_share_interactive_questions": {"akshare": get_a_share_interactive_questions},
    "get_a_share_interactive_answers": {"akshare": get_a_share_interactive_answers},
    "search_a_share_iwencai": {"iwencai": search_a_share_iwencai},
    "get_cls_telegraph": {"cls": get_cls_telegraph},
}


logger = logging.getLogger("tradingagents.dataflows.interface")


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


# News results may be reused only inside one explicitly owned analysis run.
# The localhost process is long-lived, so module lifetime is not a run boundary.
@dataclass(frozen=True)
class _NewsCacheEntry:
    result: str
    origin: CacheOrigin


_news_result_cache: dict[tuple, _NewsCacheEntry] = {}
_news_cache_namespace: ContextVar[str | None] = ContextVar(
    "tradingagents_news_cache_namespace",
    default=None,
)


@contextmanager
def news_cache_scope(run_id: str):
    """Own and destroy one run's news cache namespace."""
    token = _news_cache_namespace.set(run_id)
    try:
        yield
    finally:
        stale_keys = [key for key in _news_result_cache if key[0] == run_id]
        for key in stale_keys:
            _news_result_cache.pop(key, None)
        _news_cache_namespace.reset(token)


def _build_news_cache_key(method: str, args: tuple[Any, ...], kwargs: dict[str, Any]):
    if method not in {"get_news", "get_global_news"}:
        return None
    context = current_observation_context()
    namespace = _news_cache_namespace.get()
    if namespace is None:
        return None
    if context is not None and context.run_id != namespace:
        raise RuntimeError("news cache scope does not match the active observation run")
    vendor_config = get_vendor(get_category_for_method(method), method)
    return (
        namespace,
        method,
        vendor_config,
        tuple(str(arg) for arg in args),
        tuple(sorted((key, str(value)) for key, value in kwargs.items() if value is not None)),
    )


def route_to_vendor(method: str, *args, **kwargs):
    """Route one request and persist its normalized provenance when observed."""
    provenance = begin_data_request(method, args, kwargs)
    cache_key = _build_news_cache_key(method, args, kwargs)
    if cache_key is not None and cache_key in _news_result_cache:
        entry = _news_result_cache[cache_key]
        origin_is_complete = bool(entry.origin.vendor_call_ids and entry.origin.artifact_ids)
        if not provenance.active or origin_is_complete:
            provenance.cache_hit(cache_key=cache_key, origin=entry.origin)
            return entry.result
    try:
        result = _route_to_vendor_impl(method, *args, _provenance=provenance, **kwargs)
    except Exception as exc:
        provenance.request_failed(exc)
        raise
    origin = provenance.complete(result)
    if cache_key is not None and (not provenance.active or origin is not None):
        _news_result_cache[cache_key] = _NewsCacheEntry(
            result=result,
            origin=origin or CacheOrigin((), (), time.monotonic()),
        )
    return result


def _route_to_vendor_impl(
    method: str,
    *args,
    _provenance: DataRequestObservation,
    **kwargs,
):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(",") if v.strip()]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # An explicit vendor choice that names no real vendor is a config error:
    # surface it instead of silently trying every vendor in VENDOR_METHODS.
    if vendor_config != "default":
        # A vendor name that is not a known vendor at all (typo, e.g.
        # "bogus_vendor") is a config error: surface it. Vendors that are
        # valid but not wired for this particular method (e.g. tushare for
        # get_indicators) are handled by the fallback chain below, not here.
        known_vendors = set(VENDOR_LIST)
        unknown = [v for v in primary_vendors if v not in known_vendors]
        if unknown:
            raise ValueError(
                f"Unknown vendor(s) configured for '{method}': {', '.join(unknown)}. "
                f"Known vendors: {', '.join(VENDOR_LIST)}"
            )

    if method in {"get_news", "get_global_news"}:
        return _route_news_to_vendors(
            method,
            primary_vendors,
            *args,
            _provenance=_provenance,
            **kwargs,
        )

    # Build fallback chain. "default" keeps the resilient full-chain behavior.
    # An explicit vendor choice is honored strictly: only the configured
    # vendors are tried, so a healthy unchosen vendor is NOT silently used
    # (#988). Transient errors (rate limit / network) still opt in to the
    # remaining vendors as an implicit safety net - see the recoverable branch.
    if vendor_config == "default":
        fallback_vendors = list(VENDOR_METHODS[method].keys())
    else:
        fallback_vendors = primary_vendors.copy()

    recoverable_errors = []
    incomplete_primary: tuple[str, Any, str] | None = None
    last_no_data: NoMarketDataError | None = None
    first_error: Exception | None = None
    # True once a transient error (rate limit / network) pulled in a vendor
    # outside the explicit chain. When the whole chain still fails after that,
    # we surface an aggregated DataUnavailableError rather than re-raising the
    # single primary error, because more than one vendor was actually tried.
    implicit_fallback_triggered = False

    for index, vendor in enumerate(fallback_vendors):
        if vendor not in VENDOR_METHODS[method]:
            continue
        if _should_skip_vendor_for_symbol(method, vendor, args):
            continue

        cooldown = _vendor_health.cooldown_for(
            vendor=vendor,
            market=_market_for_request(args, method),
            capability=method,
        )
        if cooldown is not None:
            attempt = _provenance.start_attempt(
                vendor,
                fallback_chain=tuple(fallback_vendors),
                emit_started=False,
            )
            reason = (
                f"cooldown active for {cooldown.remaining_seconds(time.monotonic()):.0f}s "
                f"after {cooldown.reason}"
            )
            _provenance.skip(attempt, reason=reason)
            _emit_data_progress(
                "skipped",
                method,
                vendor,
                args,
                reason,
                vendor_call_id=attempt.vendor_call_id,
            )
            recoverable_errors.append((vendor, DataSourceUnavailableError(reason)))
            if last_no_data is None and args:
                last_no_data = NoMarketDataError(
                    symbol=str(args[0]),
                    detail=f"vendor {vendor} in cooldown after {cooldown.reason}",
                )
            # A stored cooldown only represents a prior transient failure. It
            # gets the same implicit safety-net fallback as a live 429/network
            # failure, even when the user explicitly selected one primary.
            for extra in VENDOR_METHODS[method]:
                if extra not in fallback_vendors:
                    fallback_vendors.append(extra)
                    implicit_fallback_triggered = True
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        attempt = _provenance.start_attempt(vendor, fallback_chain=tuple(fallback_vendors))
        try:
            with _provenance.attempt_scope(attempt):
                _emit_data_progress("start", method, vendor, args)
                result = impl_func(*args, **kwargs)
        except NoMarketDataError as e:
            artifact_id = _provenance.fail(attempt, e)
            last_no_data = e
            _emit_data_progress(
                "failure",
                method,
                vendor,
                args,
                str(e),
                vendor_call_id=attempt.vendor_call_id,
                artifact_id=artifact_id,
            )
            logger.warning("vendor %s reported no market data for %s: %s", vendor, method, e)
            recoverable_errors.append((vendor, e))
            if first_error is None:
                first_error = e
            continue
        except Exception as exc:
            artifact_id = _provenance.fail(attempt, exc)
            if _is_recoverable_vendor_error(vendor, exc):
                _record_vendor_failure(vendor, method, args, exc)
                _emit_data_progress(
                    "failure",
                    method,
                    vendor,
                    args,
                    _summarize_vendor_error(exc),
                    vendor_call_id=attempt.vendor_call_id,
                    artifact_id=artifact_id,
                )
                # Log the real error so a broken primary is visible in logs,
                # not masked by a later fallback's no-data sentinel (#989).
                logger.warning("vendor %s failed for %s: %s", vendor, method, exc)
                recoverable_errors.append((vendor, exc))
                if first_error is None:
                    first_error = exc
                # Transient errors (rate limit / network) opt in to the
                # remaining vendors even under an explicit single-vendor
                # config: a throttle is temporary, so an unchosen vendor is
                # worth trying. NoMarketDataError / not-configured errors do
                # NOT trigger this - they reflect data/config state that
                # trying another unchosen vendor would mask (#988).
                if _is_transient_vendor_error(exc):
                    for extra in VENDOR_METHODS[method]:
                        if extra not in fallback_vendors:
                            fallback_vendors.append(extra)
                            implicit_fallback_triggered = True
                continue
            raise

        if _is_missing_required_data_result(result):
            summary = str(result).strip()[:300]
            artifact_id = _provenance.fail(attempt, summary)
            _emit_data_progress(
                "failure",
                method,
                vendor,
                args,
                summary,
                vendor_call_id=attempt.vendor_call_id,
                artifact_id=artifact_id,
            )
            recoverable_errors.append((vendor, ChinaDataUnavailableError(summary)))
            continue

        if _should_supplement_yfinance_result(method, vendor, args, result):
            artifact_id = _provenance.succeed(attempt, result)
            reason = _summarize_yfinance_incompleteness(method, args, result)
            incomplete_primary = (vendor, result, reason)
            recoverable_errors.append((vendor, ChinaDataUnavailableError(reason)))
            next_vendor = _next_china_supplemental_vendor(fallback_vendors[index + 1 :])
            if next_vendor:
                _emit_supplement_progress(method, vendor, next_vendor)
            continue

        if incomplete_primary and _is_china_supplemental_vendor(vendor):
            artifact_id = _provenance.succeed(attempt, result)
            _record_vendor_success(vendor, method, args)
            _emit_data_progress(
                "success",
                method,
                vendor,
                args,
                _summarize_data_result(method, result),
                vendor_call_id=attempt.vendor_call_id,
                artifact_id=artifact_id,
            )
            return _format_supplemental_result(
                method=method,
                primary_vendor=incomplete_primary[0],
                primary_result=incomplete_primary[1],
                reason=incomplete_primary[2],
                supplemental_vendor=vendor,
                supplemental_result=result,
            )

        artifact_id = _provenance.succeed(attempt, result)
        _record_vendor_success(vendor, method, args)
        _emit_data_progress(
            "success",
            method,
            vendor,
            args,
            _summarize_data_result(method, result),
            vendor_call_id=attempt.vendor_call_id,
            artifact_id=artifact_id,
        )
        return result

    # If any vendor reported "no data", the symbol is genuinely unavailable.
    # Return one explicit, instructive sentinel rather than a vendor-specific
    # empty string, so the agent reports "unavailable" instead of inventing a
    # value. This takes precedence over incidental fallback errors.
    if last_no_data is not None:
        sym = last_no_data.symbol
        canonical = last_no_data.canonical
        resolved = "" if canonical == sym else f" (resolved to '{canonical}')"
        detail = (last_no_data.detail or "").strip()
        detail_part = f" Last observed detail: {detail}." if detail else ""
        return (
            f"NO_DATA_AVAILABLE: No market data found for '{sym}'{resolved} from "
            f"any configured vendor. The symbol may be invalid, delisted, or not "
            f"covered by Yahoo Finance / Alpha Vantage. Do not estimate or "
            f"fabricate values — report that data is unavailable for this symbol."
            f"{detail_part}"
        )

    if incomplete_primary:
        message = _format_incomplete_primary_result(
            method=method,
            primary_vendor=incomplete_primary[0],
            primary_result=incomplete_primary[1],
            reason=incomplete_primary[2],
            errors=recoverable_errors,
        )
        if _should_halt_on_missing_data(method):
            raise DataUnavailableError(message)
        return message

    if recoverable_errors:
        # Optional categories degrade to a sentinel so the analysis proceeds.
        if not _should_halt_on_missing_data(method):
            return _format_vendor_unavailable_message(method, recoverable_errors, category)
        # Core category: a single configured vendor that fails with no fallback
        # tried must surface its real error (a broken primary should be loud,
        # not silently repackaged). When more than one vendor was tried - either
        # an explicit multi-vendor chain or an implicit fallback - aggregate the
        # failures into DataUnavailableError so every vendor's reason is visible.
        if (
            len(recoverable_errors) == 1
            and not implicit_fallback_triggered
            and first_error is not None
        ):
            raise recoverable_errors[0][1]
        message = _format_vendor_unavailable_message(method, recoverable_errors, category)
        raise DataUnavailableError(message)

    raise RuntimeError(f"No available vendor for '{method}'")


def _route_news_to_vendors(
    method: str,
    vendors: list[str],
    *args,
    _provenance: DataRequestObservation,
    **kwargs,
) -> str:
    """Fetch news from configured sources and curate a compact source-labeled package."""
    configured_vendors = [vendor for vendor in vendors if vendor != "default"]
    if not configured_vendors:
        configured_vendors = ["tavily", "yfinance", "alpha_vantage"]
    successes: list[tuple[str, Any]] = []
    errors: list[tuple[str, Exception | str]] = []

    for vendor in configured_vendors:
        if vendor not in VENDOR_METHODS[method]:
            message = f"vendor does not support {method}"
            attempt = _provenance.start_attempt(vendor, fallback_chain=tuple(configured_vendors))
            artifact_id = _provenance.fail(attempt, message)
            _emit_data_progress(
                "failure",
                method,
                vendor,
                args,
                message,
                vendor_call_id=attempt.vendor_call_id,
                artifact_id=artifact_id,
            )
            errors.append((vendor, message))
            continue

        cooldown = _vendor_health.cooldown_for(
            vendor=vendor,
            market=_market_for_request(args, method),
            capability=method,
        )
        if cooldown is not None:
            attempt = _provenance.start_attempt(
                vendor,
                fallback_chain=tuple(configured_vendors),
                emit_started=False,
            )
            reason = (
                f"cooldown active for {cooldown.remaining_seconds(time.monotonic()):.0f}s "
                f"after {cooldown.reason}"
            )
            _provenance.skip(attempt, reason=reason)
            _emit_data_progress(
                "skipped",
                method,
                vendor,
                args,
                reason,
                vendor_call_id=attempt.vendor_call_id,
            )
            errors.append((vendor, reason))
            continue

        attempt = _provenance.start_attempt(vendor, fallback_chain=tuple(configured_vendors))
        try:
            with _provenance.attempt_scope(attempt):
                _emit_data_progress("start", method, vendor, args)
                result = VENDOR_METHODS[method][vendor](*args, **kwargs)
        except Exception as exc:
            artifact_id = _provenance.fail(attempt, exc)
            _record_vendor_failure(vendor, method, args, exc)
            _emit_data_progress(
                "failure",
                method,
                vendor,
                args,
                _summarize_vendor_error_for_news(exc),
                vendor_call_id=attempt.vendor_call_id,
                artifact_id=artifact_id,
            )
            errors.append((vendor, exc))
            continue

        if _is_error_news_result(result):
            message = _summarize_error_news_result(result)
            artifact_id = _provenance.fail(attempt, message)
            _emit_data_progress(
                "failure",
                method,
                vendor,
                args,
                message,
                vendor_call_id=attempt.vendor_call_id,
                artifact_id=artifact_id,
            )
            errors.append((vendor, message))
            continue

        if _is_empty_news_result(result):
            message = _summarize_empty_news_result(result)
            artifact_id = _provenance.fail(attempt, message)
            _emit_data_progress(
                "failure",
                method,
                vendor,
                args,
                message,
                vendor_call_id=attempt.vendor_call_id,
                artifact_id=artifact_id,
            )
            errors.append((vendor, message))
            continue
        artifact_id = _provenance.succeed(attempt, result)
        _record_vendor_success(vendor, method, args)
        _emit_data_progress(
            "success",
            method,
            vendor,
            args,
            _summarize_news_result(result),
            vendor_call_id=attempt.vendor_call_id,
            artifact_id=artifact_id,
        )
        successes.append((vendor, result))

    # Public exchange announcements use a different protocol and intentionally
    # sit behind normal news search: they are authoritative disclosures, not a
    # silent replacement for broader market coverage.  The adapter is only
    # eligible for A shares and only after every configured news provider is
    # unavailable or empty.  This is an explicit, source-labelled degradation.
    if not successes:
        fallback_vendors = _news_official_fallback_vendors(
            method, args, already_attempted=configured_vendors
        )
        for vendor in fallback_vendors:
            attempt = _provenance.start_attempt(
                vendor,
                fallback_chain=(*configured_vendors, *fallback_vendors),
            )
            try:
                with _provenance.attempt_scope(attempt):
                    _emit_data_progress("start", method, vendor, args)
                    result = VENDOR_METHODS[method][vendor](*args, **kwargs)
            except Exception as exc:
                artifact_id = _provenance.fail(attempt, exc)
                _record_vendor_failure(vendor, method, args, exc)
                _emit_data_progress(
                    "failure",
                    method,
                    vendor,
                    args,
                    _summarize_vendor_error_for_news(exc),
                    vendor_call_id=attempt.vendor_call_id,
                    artifact_id=artifact_id,
                )
                errors.append((vendor, exc))
                continue
            if _is_empty_news_result(result) or _is_error_news_result(result):
                message = (
                    _summarize_empty_news_result(result)
                    if _is_empty_news_result(result)
                    else _summarize_error_news_result(result)
                )
                artifact_id = _provenance.fail(attempt, message)
                _emit_data_progress(
                    "failure",
                    method,
                    vendor,
                    args,
                    message,
                    vendor_call_id=attempt.vendor_call_id,
                    artifact_id=artifact_id,
                )
                errors.append((vendor, message))
                continue
            artifact_id = _provenance.succeed(attempt, result)
            _record_vendor_success(vendor, method, args)
            _emit_data_progress(
                "success",
                method,
                vendor,
                args,
                _summarize_news_result(result),
                vendor_call_id=attempt.vendor_call_id,
                artifact_id=artifact_id,
            )
            successes.append((vendor, result))

    if successes:
        # Extract date window for staleness filtering (args are ticker, start_date, end_date for get_news)
        start_date = str(args[1]) if len(args) >= 2 else ""
        end_date = str(args[2]) if len(args) >= 3 else ""
        return _format_curated_news(method, successes, errors, start_date, end_date)

    details = (
        "; ".join(f"{vendor}: {err}" for vendor, err in errors) or "no news vendors configured"
    )
    return f"No curated news found for '{method}'. Source status: {details}."


def _news_official_fallback_vendors(
    method: str,
    args: tuple[Any, ...],
    *,
    already_attempted: list[str],
) -> list[str]:
    """Return only public, configured source-priority cross-protocol fallbacks."""
    if method != "get_news" or not args or not is_a_share_ticker(str(args[0])):
        return []
    if not get_config().get("a_share_news_official_fallback_enabled", True):
        return []
    return [
        vendor
        for vendor in ("china_exchange",)
        if vendor not in already_attempted and vendor in VENDOR_METHODS[method]
    ]


_A_SHARE_TICKER_CAPABILITIES = {
    "get_stock_data",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_a_share_valuation",
    "get_a_share_research_reports",
    "get_a_share_eps_forecast",
    "get_a_share_concept_blocks",
    "get_a_share_hot_concept",
    "get_a_share_capital_flow",
    "get_a_share_margin_financing",
    "get_a_share_northbound_holdings",
    "get_a_share_insider_trades",
    "get_a_share_exchange_announcements",
    "get_a_share_bulk_trades",
    "get_a_share_shareholder_counts",
    "get_a_share_lockup_releases",
    "get_a_share_dragon_tiger",
    "get_a_share_interactive_questions",
}


_A_SHARE_NON_TICKER_CAPABILITIES = {
    "get_a_share_limit_up_ladder",
    "get_a_share_daily_dragon_tiger",
    "get_a_share_industry_ranking",
    "get_a_share_option_tquote",
    "get_a_share_option_greeks",
    "get_a_share_hot_list",
    "get_a_share_break_board_pool",
    "get_a_share_limit_down_pool",
    "get_a_share_prev_limit_up_pool",
    "get_a_share_northbound_flow",
    "get_china_macro_indicators",
    "get_a_share_interactive_answers",
    "search_a_share_iwencai",
    "get_cls_telegraph",
}


def _should_skip_vendor_for_symbol(method: str, vendor: str, args: tuple[Any, ...]) -> bool:
    """Route A-share tickers away from overseas vendors and vice versa.

    Uses the ``VENDOR_MARKETS`` capability matrix: a vendor is skipped when
    the request's market is not among the vendor's declared markets. China-only
    providers (tushare/akshare/eastmoney/china_exchange/iwencai/cls) are skipped
    for non-A-share tickers; yfinance is skipped for A-share tickers (requires
    VPN, poor coverage, wastes ~15s on rate-limit retries when tushare/akshare
    are the correct primary sources).

    Date-only and query-only A-share capabilities do not have a ticker in
    position zero, so they are recognised by method rather than being skipped
    by the generic ticker check.
    """
    if method not in _A_SHARE_TICKER_CAPABILITIES:
        return False
    if not args:
        return False
    is_a_share = is_a_share_ticker(str(args[0]))
    markets = VENDOR_MARKETS.get(vendor, frozenset({"a_share", "global"}))
    if is_a_share:
        return "a_share" not in markets
    return "global" not in markets


def _market_for_request(args: tuple[Any, ...], method: str | None = None) -> str:
    if method in _A_SHARE_NON_TICKER_CAPABILITIES:
        return "a_share"
    if args and is_a_share_ticker(str(args[0])):
        return "a_share"
    return "global"
