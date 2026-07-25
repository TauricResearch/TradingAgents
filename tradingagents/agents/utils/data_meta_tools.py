"""Allowlisted, bounded data bundles for analyst tool calls.

The analyst-facing interface is deliberately smaller than the vendor layer.
An LLM may describe the question it wants answered, but it cannot name a
Python callable, a provider, or arbitrary arguments.  This module maps that
description to a fixed, reviewable capability catalogue and returns a typed
envelope suitable for an agent report.

The individual data tools remain available when an analyst needs one precise
query.  These bundles are for the common case where several independent data
views are required and can be fetched concurrently.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Literal

from langchain_core.tools import tool

from tradingagents.agents.utils.tool_guard import guard_target_ticker
from tradingagents.dataflows.errors import (
    DataSourceUnavailableError,
    VendorError,
)
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.market_data_validator import build_verified_market_snapshot
from tradingagents.dataflows.ticker_utils import is_a_share_ticker

BundleFocus = Literal["market", "fundamentals", "news"]

# A bundle must stay small enough that one agent turn is predictable.  This is
# a concurrency limit, rather than a free-for-all implementation detail.
MAX_CAPABILITIES_PER_BUNDLE = 4
MAX_PARALLEL_CAPABILITIES = 3
MAX_RESULT_CHARS = 12_000


@dataclass(frozen=True)
class Capability:
    """One reviewed data capability exposed by a meta tool.

    ``runner`` is populated from this module only; request text is never
    turned into an import path or a callable name.
    """

    id: str
    route_method: str
    focus: BundleFocus
    runner: Callable[[str, str, str], str]
    keywords: tuple[str, ...] = ()
    a_share_only: bool = False
    default: bool = False


def _start_date(curr_date: str, look_back_days: int = 30) -> str:
    try:
        return (date.fromisoformat(curr_date) - timedelta(days=look_back_days)).isoformat()
    except ValueError:
        # The underlying tools will report the invalid date in their normal
        # validation path.  Do not silently substitute today's date.
        return curr_date


def _market_snapshot(symbol: str, curr_date: str, _request: str) -> str:
    return build_verified_market_snapshot(symbol, curr_date, 30)


def _price_history(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_stock_data", symbol, _start_date(curr_date), curr_date)


def _rsi_indicator(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_indicators", symbol, "rsi", curr_date, 30)


def _macd_indicator(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_indicators", symbol, "macd", curr_date, 30)


def _capital_flow(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_a_share_capital_flow", symbol, _start_date(curr_date), curr_date)


def _margin_financing(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_a_share_margin_financing", symbol, _start_date(curr_date), curr_date)


def _northbound_flow(_symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_a_share_northbound_flow", _start_date(curr_date), curr_date)


def _northbound_holdings(symbol: str, _curr_date: str, _request: str) -> str:
    return route_to_vendor("get_a_share_northbound_holdings", symbol)


def _insider_trades(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_a_share_insider_trades", symbol, _start_date(curr_date), curr_date)


def _dragon_tiger(symbol: str, _curr_date: str, _request: str) -> str:
    return route_to_vendor("get_a_share_dragon_tiger", symbol)


def _announcements(symbol: str, _curr_date: str, _request: str) -> str:
    return route_to_vendor("get_a_share_exchange_announcements", symbol)


def _fundamentals(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_fundamentals", symbol, curr_date)


def _balance_sheet(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_balance_sheet", symbol, "quarterly", curr_date)


def _cashflow(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_cashflow", symbol, "quarterly", curr_date)


def _income_statement(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_income_statement", symbol, "quarterly", curr_date)


def _company_news(symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_news", symbol, _start_date(curr_date, 7), curr_date)


def _global_news(_symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_global_news", curr_date, 7, 10)


def _macro_cpi(_symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_macro_indicators", "cpi", curr_date, 365)


def _macro_rates(_symbol: str, curr_date: str, _request: str) -> str:
    return route_to_vendor("get_macro_indicators", "fed_funds_rate", curr_date, 365)


def _china_macro(_symbol: str, _curr_date: str, _request: str) -> str:
    return route_to_vendor("get_china_macro_indicators", "gdp,cpi,pmi,money_supply,lpr")


_CAPABILITIES: tuple[Capability, ...] = (
    Capability("verified_market_snapshot", "verified_market_snapshot", "market", _market_snapshot, default=True),
    Capability("price_history", "get_stock_data", "market", _price_history, default=True),
    Capability("rsi", "get_indicators", "market", _rsi_indicator, ("rsi", "超买", "超卖", "momentum", "动量")),
    Capability("macd", "get_indicators", "market", _macd_indicator, ("macd", "趋势", "trend", "动量")),
    Capability("capital_flow", "get_a_share_capital_flow", "market", _capital_flow, ("资金", "资金流", "capital flow"), True),
    Capability("margin_financing", "get_a_share_margin_financing", "market", _margin_financing, ("融资", "融券", "margin"), True),
    Capability("northbound_flow", "get_a_share_northbound_flow", "market", _northbound_flow, ("北向", "陆股通", "northbound"), True),
    Capability("northbound_holdings", "get_a_share_northbound_holdings", "market", _northbound_holdings, ("北向持仓", "北向持股", "陆股通持仓"), True),
    Capability("insider_trades", "get_a_share_insider_trades", "market", _insider_trades, ("董监高", "高管增持", "高管减持", "insider"), True),
    Capability("dragon_tiger", "get_a_share_dragon_tiger", "market", _dragon_tiger, ("龙虎榜", "dragon tiger"), True),
    Capability("exchange_announcements", "get_a_share_exchange_announcements", "market", _announcements, ("公告", "announcement"), True),
    Capability("fundamentals", "get_fundamentals", "fundamentals", _fundamentals, default=True),
    Capability("balance_sheet", "get_balance_sheet", "fundamentals", _balance_sheet, ("资产负债", "balance sheet", "debt", "负债"), default=True),
    Capability("cashflow", "get_cashflow", "fundamentals", _cashflow, ("现金流", "cash flow", "free cash"), default=True),
    Capability("income_statement", "get_income_statement", "fundamentals", _income_statement, ("利润表", "income statement", "revenue", "营收", "利润"), default=True),
    Capability("company_news", "get_news", "news", _company_news, default=True),
    Capability("global_news", "get_global_news", "news", _global_news, ("宏观", "global", "market-wide", "行业", "sector")),
    Capability("macro_cpi", "get_macro_indicators", "news", _macro_cpi, ("cpi", "inflation", "通胀")),
    Capability("macro_rates", "get_macro_indicators", "news", _macro_rates, ("rate", "rates", "利率", "fed", "美联储")),
    Capability("china_macro", "get_china_macro_indicators", "news", _china_macro, ("中国宏观", "中国经济", "中国通胀", "中国pmi", "经济周期", "景气"), True),
)


def _normalized_request(request: str) -> str:
    return re.sub(r"\s+", " ", request.strip().lower())


def select_capabilities(focus: BundleFocus, symbol: str, request: str) -> list[Capability]:
    """Map natural-language intent onto the fixed capability catalogue.

    Defaults make the tool useful even for a terse request.  Keyword matches
    add only approved supplemental views and the result is capped in a stable
    catalogue order so the same input is replayable.
    """

    normalized = _normalized_request(request)
    is_a_share = is_a_share_ticker(symbol)
    eligible = [
        capability
        for capability in _CAPABILITIES
        if capability.focus == focus
        and (not capability.a_share_only or is_a_share)
    ]
    # Explicitly requested views take precedence over generic defaults.  A
    # capital-flow question should not lose its A-share supplement simply
    # because snapshot/price/technical defaults already consumed the budget.
    selected = [
        capability
        for capability in eligible
        if any(keyword in normalized for keyword in capability.keywords)
    ]
    selected.extend(
        capability for capability in eligible if capability.default and capability not in selected
    )
    selected = selected[:MAX_CAPABILITIES_PER_BUNDLE]
    return selected


def _public_error_type(exc: Exception) -> str:
    if isinstance(exc, (DataSourceUnavailableError, VendorError)):
        return "source_unavailable"
    if isinstance(exc, (TypeError, ValueError)):
        return "invalid_request"
    return "source_failed"


def _result_status(result: str) -> str:
    lowered = result.strip().lower()
    if lowered.startswith("no_data_available:") or lowered.startswith("data unavailable"):
        return "unavailable"
    if lowered.startswith("no curated news found"):
        return "unavailable"
    return "ok"


def _execute(
    capability: Capability, symbol: str, curr_date: str, request: str
) -> dict[str, object]:
    """Execute a known capability and redact provider-specific failure text."""

    try:
        result = str(capability.runner(symbol, curr_date, request))
    except Exception as exc:  # router failures are converted into the envelope
        return {
            "capability": capability.id,
            "route_method": capability.route_method,
            "status": "error",
            "error_type": _public_error_type(exc),
            "message": "The requested data capability is currently unavailable.",
        }
    status = _result_status(result)
    if status == "unavailable":
        return {
            "capability": capability.id,
            "route_method": capability.route_method,
            "status": status,
            "message": "No usable data was returned for this capability.",
        }
    return {
        "capability": capability.id,
        "route_method": capability.route_method,
        "status": status,
        "data": result[:MAX_RESULT_CHARS],
        "truncated": len(result) > MAX_RESULT_CHARS,
    }


def run_data_bundle(
    focus: BundleFocus,
    symbol: str,
    curr_date: str,
    request: str,
) -> str:
    """Return a compact JSON envelope for an allowlisted data bundle.

    The envelope carries capability-level route provenance and public error
    categories.  It intentionally omits raw provider exception text, which
    can contain implementation details, credentials, or unstable HTML.
    """

    selected = select_capabilities(focus, symbol, request)
    if not selected:
        return json.dumps(
            {
                "focus": focus,
                "symbol": symbol,
                "status": "invalid_request",
                "message": "No approved data capability matches this request.",
                "results": [],
            },
            ensure_ascii=False,
        )

    result_by_id: dict[str, dict[str, object]] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_CAPABILITIES, len(selected))) as executor:
        futures = {
            executor.submit(_execute, capability, symbol, curr_date, request): capability.id
            for capability in selected
        }
        for future in as_completed(futures):
            item = future.result()
            result_by_id[item["capability"]] = item

    # Preserve selected order after concurrent work completes; LLM input and
    # replay output must not depend on scheduler timing.
    results = [result_by_id[capability.id] for capability in selected]
    status = "ok" if any(item["status"] == "ok" for item in results) else "degraded"
    return json.dumps(
        {
            "focus": focus,
            "symbol": symbol,
            "as_of": curr_date,
            "status": status,
            "provenance": {
                "selection": "allowlisted_keyword_router_v1",
                "parallelism_limit": MAX_PARALLEL_CAPABILITIES,
            },
            "results": results,
        },
        ensure_ascii=False,
    )


@tool
@guard_target_ticker("symbol")
def get_market_research_bundle(
    symbol: Annotated[str, "ticker symbol of the instrument"],
    curr_date: Annotated[str, "analysis date in yyyy-mm-dd format"],
    request: Annotated[str, "plain-language market-data question; it selects only reviewed capabilities"],
) -> str:
    """Fetch a bounded market-data bundle selected from an approved catalogue.

    Use this when price history, verified price facts, technical indicators, or
    A-share capital-flow/announcement context are jointly needed.  The request
    cannot choose a provider or invoke arbitrary code.
    """

    return run_data_bundle("market", symbol, curr_date, request)


@tool
@guard_target_ticker("symbol")
def get_fundamentals_research_bundle(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "analysis date in yyyy-mm-dd format"],
    request: Annotated[str, "plain-language fundamentals question; it selects only reviewed capabilities"],
) -> str:
    """Fetch a bounded, allowlisted company-fundamentals bundle in parallel."""

    return run_data_bundle("fundamentals", symbol, curr_date, request)


@tool
@guard_target_ticker("symbol")
def get_news_research_bundle(
    symbol: Annotated[str, "ticker symbol of the instrument"],
    curr_date: Annotated[str, "analysis date in yyyy-mm-dd format"],
    request: Annotated[str, "plain-language news or macro question; it selects only reviewed capabilities"],
) -> str:
    """Fetch a bounded, allowlisted company-news and macro-news bundle."""

    return run_data_bundle("news", symbol, curr_date, request)
