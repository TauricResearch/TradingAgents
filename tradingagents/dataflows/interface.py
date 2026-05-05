import json
import os
import re
from typing import Annotated, Any
from io import StringIO

import pandas as pd

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .tavily_news import (
    TavilyUnavailableError,
    get_news_tavily,
    get_global_news_tavily,
)
from .china_data import (
    ChinaDataUnavailableError,
    get_stock_tushare,
    get_stock_akshare,
    get_fundamentals_tushare,
    get_fundamentals_akshare,
    get_balance_sheet_tushare,
    get_cashflow_tushare,
    get_income_statement_tushare,
)
from .ticker_utils import is_a_share_ticker
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from yfinance.exceptions import YFRateLimitError

# Configuration and routing logic
from .config import get_config
from .progress import emit_progress

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
    }
}

VENDOR_LIST = [
    "tushare",
    "akshare",
    "tavily",
    "yfinance",
    "alpha_vantage",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
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
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "tushare": get_cashflow_tushare,
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "tushare": get_income_statement_tushare,
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "tavily": get_news_tavily,
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
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
}


class DataUnavailableError(RuntimeError):
    """Raised when required analysis data is unavailable from all configured vendors."""

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

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',') if v.strip()]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    if method in {"get_news", "get_global_news"}:
        return _route_news_to_vendors(method, primary_vendors, *args, **kwargs)

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    recoverable_errors = []
    incomplete_primary: tuple[str, Any, str] | None = None

    for index, vendor in enumerate(fallback_vendors):
        if vendor not in VENDOR_METHODS[method]:
            continue
        if _should_skip_vendor_for_symbol(vendor, args):
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        _emit_data_progress("start", method, vendor, args)
        try:
            result = impl_func(*args, **kwargs)
        except Exception as exc:
            if _is_recoverable_vendor_error(vendor, exc):
                _emit_data_progress("failure", method, vendor, args, _summarize_vendor_error(exc))
                recoverable_errors.append((vendor, exc))
                continue
            raise

        if _is_missing_required_data_result(result):
            summary = str(result).strip()[:300]
            _emit_data_progress("failure", method, vendor, args, summary)
            recoverable_errors.append((vendor, ChinaDataUnavailableError(summary)))
            continue

        if _should_supplement_yfinance_result(method, vendor, args, result):
            reason = _summarize_yfinance_incompleteness(method, args, result)
            incomplete_primary = (vendor, result, reason)
            recoverable_errors.append((vendor, ChinaDataUnavailableError(reason)))
            next_vendor = _next_china_supplemental_vendor(fallback_vendors[index + 1 :])
            if next_vendor:
                _emit_supplement_progress(method, vendor, next_vendor)
            continue

        if incomplete_primary and _is_china_supplemental_vendor(vendor):
            _emit_data_progress("success", method, vendor, args, _summarize_data_result(method, result))
            return _format_supplemental_result(
                method=method,
                primary_vendor=incomplete_primary[0],
                primary_result=incomplete_primary[1],
                reason=incomplete_primary[2],
                supplemental_vendor=vendor,
                supplemental_result=result,
            )

        _emit_data_progress("success", method, vendor, args, _summarize_data_result(method, result))
        return result

    if incomplete_primary:
        return _format_incomplete_primary_result(
            method=method,
            primary_vendor=incomplete_primary[0],
            primary_result=incomplete_primary[1],
            reason=incomplete_primary[2],
            errors=recoverable_errors,
        )

    if recoverable_errors:
        message = _format_vendor_unavailable_message(method, recoverable_errors)
        if _should_halt_on_missing_data(method):
            raise DataUnavailableError(message)
        return message

    raise RuntimeError(f"No available vendor for '{method}'")


def _route_news_to_vendors(method: str, vendors: list[str], *args, **kwargs) -> str:
    """Fetch news from configured sources and curate a compact source-labeled package."""
    configured_vendors = [vendor for vendor in vendors if vendor != "default"]
    if not configured_vendors:
        configured_vendors = ["tavily", "yfinance", "alpha_vantage"]
    successes: list[tuple[str, Any]] = []
    errors: list[tuple[str, Exception | str]] = []

    for vendor in configured_vendors:
        if vendor not in VENDOR_METHODS[method]:
            message = f"vendor does not support {method}"
            _emit_data_progress("failure", method, vendor, args, message)
            errors.append((vendor, message))
            continue

        _emit_data_progress("start", method, vendor, args)
        try:
            result = VENDOR_METHODS[method][vendor](*args, **kwargs)
        except Exception as exc:
            _emit_data_progress("failure", method, vendor, args, _summarize_vendor_error_for_news(exc))
            errors.append((vendor, exc))
            continue

        if _is_error_news_result(result):
            message = _summarize_error_news_result(result)
            _emit_data_progress("failure", method, vendor, args, message)
            errors.append((vendor, message))
            continue

        if _is_empty_news_result(result):
            message = _summarize_empty_news_result(result)
            _emit_data_progress("failure", method, vendor, args, message)
            errors.append((vendor, message))
            continue
        _emit_data_progress("success", method, vendor, args, _summarize_news_result(result))
        successes.append((vendor, result))

    if successes:
        return _format_curated_news(method, successes, errors)

    details = "; ".join(f"{vendor}: {err}" for vendor, err in errors) or "no news vendors configured"
    return f"No curated news found for '{method}'. Source status: {details}."


def _is_empty_news_result(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, dict) and result.get("source") == "tavily":
        return len(result.get("items") or []) == 0
    text = str(result).strip()
    if not text:
        return True
    lowered = text.lower()
    return lowered.startswith("no news found") or lowered.startswith("no global news found")


def _emit_data_progress(
    stage: str,
    method: str,
    vendor: str,
    args: tuple[Any, ...],
    detail: str | None = None,
) -> None:
    labels = {
        "start": "数据调用开始",
        "success": "数据调用成功",
        "failure": "数据调用失败",
    }
    context = _format_progress_context(method, args)
    parts = [f"{labels.get(stage, stage)}：{method}", vendor]
    if context and stage == "start":
        parts.append(context)
    if detail:
        parts.append(_sanitize_progress_text(detail))
    emit_progress(stage, method, vendor, " | ".join(parts))


def _emit_supplement_progress(method: str, primary_vendor: str, next_vendor: str) -> None:
    emit_progress(
        "supplement",
        method,
        next_vendor,
        f"数据源补充：{method} | {primary_vendor} 覆盖不足，继续尝试 {next_vendor}",
    )


def _format_progress_context(method: str, args: tuple[Any, ...]) -> str:
    if not args:
        return ""
    if method in {"get_news", "get_stock_data"} and len(args) >= 3:
        return f"{args[0]} | {args[1]}~{args[2]}"
    if method == "get_global_news" and args:
        return str(args[0])
    if method in {"get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement"}:
        parts = [str(args[0])]
        if len(args) >= 2 and args[-1]:
            parts.append(str(args[-1]))
        return " | ".join(parts)
    return " | ".join(str(value) for value in args[:3])


def _summarize_news_result(result: Any) -> str:
    count = len(_extract_news_items("unknown", result))
    return f"返回 {count} 条新闻"


def _summarize_data_result(method: str, result: Any) -> str:
    if method in {"get_stock_data", "get_balance_sheet", "get_cashflow", "get_income_statement"}:
        df = _parse_csv_from_report(result)
        if df is not None:
            return f"返回 {len(df)} 行数据"
    if method == "get_fundamentals":
        return "返回基本面数据"
    return "调用完成"


def _next_china_supplemental_vendor(vendors: list[str]) -> str | None:
    for vendor in vendors:
        if _is_china_supplemental_vendor(vendor):
            return vendor
    return None


def _sanitize_progress_text(text: str) -> str:
    sanitized = str(text).replace("\n", " ").strip()
    for env_name, env_value in os.environ.items():
        if not env_value or len(env_value) < 8:
            continue
        if any(token in env_name.upper() for token in ("KEY", "TOKEN", "SECRET")):
            sanitized = sanitized.replace(env_value, "***")
    return sanitized[:220]


def _is_error_news_result(result: Any) -> bool:
    if result is None or isinstance(result, (dict, list)):
        return False
    lowered = str(result).strip().lower()
    return lowered.startswith("error fetching news") or lowered.startswith("error fetching global news")


def _summarize_empty_news_result(result: Any) -> str:
    if isinstance(result, dict) and result.get("source") == "tavily":
        return "Tavily returned no results"
    return str(result).strip()[:300] or "empty result"


def _summarize_error_news_result(result: Any) -> str:
    return str(result).strip()[:300] or "source returned an error"


def _format_curated_news(
    method: str,
    successes: list[tuple[str, Any]],
    errors: list[tuple[str, Exception | str]],
) -> str:
    cfg = get_config()
    max_items = int(cfg.get("news_curator_max_items", 10))
    items: list[dict[str, Any]] = []
    for vendor, result in successes:
        items.extend(_extract_news_items(vendor, result))

    curated = _dedupe_news_items(items)[:max_items]
    sections = [
        "## Curated News Package",
        f"Method: `{method}`",
        "Sources used: " + ", ".join(vendor for vendor, _ in successes),
    ]

    if errors:
        sections.append(
            "Source status: "
            + "; ".join(f"{vendor}: {_summarize_vendor_error_for_news(err)}" for vendor, err in errors)
        )

    if not curated:
        sections.append("No parseable news items were found, but at least one source returned data.")
        for vendor, result in successes:
            sections.append(f"### Raw {vendor} result\n{str(result)[:2000]}")
        return "\n\n".join(sections)

    sections.append(
        f"Curator retained {len(curated)} item(s) after source labeling, deduplication, and max item limiting."
    )
    for idx, item in enumerate(curated, start=1):
        title = item.get("title") or "Untitled"
        source = item.get("source") or "unknown"
        publisher = item.get("publisher") or source
        score = item.get("score")
        score_part = f", score: {score:.3f}" if isinstance(score, (float, int)) else ""
        body = [f"### {idx}. {title} (source: {source}, publisher: {publisher}{score_part})"]
        if item.get("published"):
            body.append(f"Published: {item['published']}")
        if item.get("content"):
            body.append(str(item["content"]).strip())
        if item.get("url"):
            body.append(f"Link: {item['url']}")
        sections.append("\n".join(body))

    return "\n\n".join(sections)


def _extract_news_items(vendor: str, result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict) and result.get("source") == "tavily":
        return [dict(item, source="tavily") for item in result.get("items", [])]

    if isinstance(result, (dict, list)):
        return _extract_json_news_items(vendor, result)

    text = str(result)
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        parsed = None

    if parsed is not None:
        return _extract_json_news_items(vendor, parsed)

    return _extract_markdown_news_items(vendor, text)


def _extract_json_news_items(vendor: str, data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        records = data.get("feed") or data.get("results") or data.get("items") or []
    elif isinstance(data, list):
        records = data
    else:
        records = []

    items = []
    for record in records:
        if not isinstance(record, dict):
            continue
        title = record.get("title") or record.get("headline") or record.get("summary")
        if not title:
            continue
        items.append(
            {
                "title": title,
                "url": record.get("url") or record.get("link") or "",
                "content": record.get("summary") or record.get("content") or "",
                "published": record.get("time_published") or record.get("published") or "",
                "publisher": record.get("source") or record.get("publisher") or vendor,
                "score": record.get("overall_sentiment_score") or record.get("score"),
                "source": vendor,
            }
        )
    return items


def _extract_markdown_news_items(vendor: str, text: str) -> list[dict[str, Any]]:
    items = []
    blocks = re.split(r"\n(?=### )", text)
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or not lines[0].startswith("### "):
            continue
        title_line = lines[0][4:].strip()
        publisher = vendor
        match = re.search(r"\(source:\s*([^)]+)\)", title_line, flags=re.IGNORECASE)
        if match:
            publisher = match.group(1).strip()
            title_line = re.sub(r"\s*\(source:\s*[^)]+\)", "", title_line, flags=re.IGNORECASE)
        link = ""
        content_lines = []
        for line in lines[1:]:
            if line.lower().startswith("link:"):
                link = line.split(":", 1)[1].strip()
            else:
                content_lines.append(line)
        items.append(
            {
                "title": title_line,
                "url": link,
                "content": " ".join(content_lines),
                "published": "",
                "publisher": publisher,
                "score": None,
                "source": vendor,
            }
        )
    return items


def _dedupe_news_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for item in sorted(items, key=lambda x: str(x.get("published") or ""), reverse=True):
        key = _news_dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _news_dedupe_key(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip().lower()
    if url:
        return re.sub(r"[?#].*$", "", url)
    title = str(item.get("title") or "").lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title)[:120]


def _summarize_vendor_error_for_news(err: Exception | str) -> str:
    return _summarize_vendor_error(err) if isinstance(err, Exception) else str(err)


def _should_supplement_yfinance_result(
    method: str,
    vendor: str,
    args: tuple[Any, ...],
    result: Any,
) -> bool:
    if vendor != "yfinance" or not args or not is_a_share_ticker(str(args[0])):
        return False
    if method not in {
        "get_stock_data",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    }:
        return False
    return _summarize_yfinance_incompleteness(method, args, result) != ""


def _summarize_yfinance_incompleteness(
    method: str,
    args: tuple[Any, ...],
    result: Any,
) -> str:
    if method == "get_stock_data":
        return _summarize_yfinance_stock_incompleteness(args, result)
    if method == "get_fundamentals":
        return _summarize_yfinance_fundamentals_incompleteness(result)
    if method in {"get_balance_sheet", "get_cashflow", "get_income_statement"}:
        return _summarize_yfinance_statement_incompleteness(result)
    return ""


def _summarize_yfinance_stock_incompleteness(args: tuple[Any, ...], result: Any) -> str:
    df = _parse_csv_from_report(result)
    if df is None or df.empty:
        return "Yahoo Finance returned no parseable OHLCV rows for this A-share."

    missing_cols = [col for col in ("Open", "High", "Low", "Close", "Volume") if col not in df.columns]
    if missing_cols:
        return f"Yahoo Finance OHLCV data is missing required columns: {', '.join(missing_cols)}."

    core = df[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce")
    null_ratio = float(core.isna().mean().max())
    if null_ratio > 0.4:
        return f"Yahoo Finance OHLCV data has too many missing core values ({null_ratio:.0%})."

    cfg = get_config()
    min_rows = int(cfg.get("a_share_yfinance_min_rows", 3))
    if len(df) < min_rows:
        return f"Yahoo Finance returned only {len(df)} OHLCV row(s), below the minimum {min_rows}."

    if len(args) >= 3:
        expected = _expected_weekday_count(str(args[1]), str(args[2]))
        if expected > 0:
            ratio = len(df) / expected
            min_ratio = float(cfg.get("a_share_yfinance_min_coverage_ratio", 0.6))
            if ratio < min_ratio:
                return (
                    f"Yahoo Finance OHLCV coverage is {ratio:.0%} "
                    f"({len(df)}/{expected} weekdays), below the configured {min_ratio:.0%} threshold."
                )

    return ""


def _summarize_yfinance_fundamentals_incompleteness(result: Any) -> str:
    text = str(result or "")
    if _is_missing_required_data_result(text):
        return "Yahoo Finance returned no fundamentals data for this A-share."
    field_count = sum(1 for line in text.splitlines() if ":" in line and not line.startswith("#"))
    min_fields = int(get_config().get("a_share_yfinance_min_fundamental_fields", 5))
    if field_count < min_fields:
        return (
            f"Yahoo Finance fundamentals contain only {field_count} populated field(s), "
            f"below the minimum {min_fields}."
        )
    return ""


def _summarize_yfinance_statement_incompleteness(result: Any) -> str:
    if _is_missing_required_data_result(result):
        return "Yahoo Finance returned no usable financial statement data for this A-share."
    df = _parse_csv_from_report(result)
    if df is None or df.empty:
        return "Yahoo Finance statement data is not parseable as a populated table."
    if len(df.columns) <= 1:
        return "Yahoo Finance statement data has no dated statement columns."
    return ""


def _parse_csv_from_report(result: Any) -> pd.DataFrame | None:
    text = str(result or "")
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    if not lines:
        return None
    try:
        return pd.read_csv(StringIO("\n".join(lines)))
    except Exception:
        return None


def _expected_weekday_count(start_date: str, end_date: str) -> int:
    try:
        dates = pd.date_range(start=start_date, end=end_date, freq="B")
    except Exception:
        return 0
    return len(dates)


def _is_china_supplemental_vendor(vendor: str) -> bool:
    return vendor in {"tushare", "akshare"}


def _format_supplemental_result(
    *,
    method: str,
    primary_vendor: str,
    primary_result: Any,
    reason: str,
    supplemental_vendor: str,
    supplemental_result: Any,
) -> str:
    return "\n\n".join(
        [
            f"# Data Package for `{method}`",
            f"Primary source: {primary_vendor}",
            f"Supplemental source: {supplemental_vendor}",
            f"Supplement reason: {reason}",
            "## Primary Source Result",
            str(primary_result),
            "## Supplemental Source Result",
            str(supplemental_result),
        ]
    )


def _format_incomplete_primary_result(
    *,
    method: str,
    primary_vendor: str,
    primary_result: Any,
    reason: str,
    errors: list[tuple[str, Exception]],
) -> str:
    source_status = "; ".join(
        f"{vendor}: {_summarize_vendor_error(exc)}" for vendor, exc in errors if vendor != primary_vendor
    )
    sections = [
        f"# Data Package for `{method}`",
        f"Primary source: {primary_vendor}",
        "Supplemental source: unavailable",
        f"Warning: {reason}",
    ]
    if source_status:
        sections.append(f"Supplemental source status: {source_status}")
    sections.extend(["## Primary Source Result", str(primary_result)])
    return "\n\n".join(sections)


def _should_skip_vendor_for_symbol(vendor: str, args: tuple[Any, ...]) -> bool:
    if vendor not in {"tushare", "akshare"} or not args:
        return False
    return not is_a_share_ticker(str(args[0]))


def _is_missing_required_data_result(result: Any) -> bool:
    if result is None:
        return True
    if hasattr(result, "empty") and getattr(result, "empty"):
        return True
    if isinstance(result, dict):
        return not bool(result) or any(
            key in result for key in ("Error Message", "Note", "Information")
        )
    text = str(result).strip()
    if not text:
        return True
    lowered = text.lower()
    missing_prefixes = (
        "no data found",
        "no fundamentals data found",
        "no balance sheet data found",
        "no cash flow data found",
        "no income statement data found",
        "error retrieving",
        "error getting",
        "data unavailable",
    )
    return lowered.startswith(missing_prefixes)


def _should_halt_on_missing_data(method: str) -> bool:
    cfg = get_config()
    if not cfg.get("halt_on_missing_data", True):
        return False
    return method in {
        "get_stock_data",
        "get_indicators",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    }


def _is_recoverable_vendor_error(vendor: str, exc: Exception) -> bool:
    """Return True when another configured vendor should be tried."""
    if isinstance(
        exc,
        (
            AlphaVantageRateLimitError,
            TavilyUnavailableError,
            YFRateLimitError,
            ChinaDataUnavailableError,
        ),
    ):
        return True

    return (
        vendor in {"alpha_vantage", "tavily", "tushare", "akshare"}
        and isinstance(exc, ValueError)
        and (
            "ALPHA_VANTAGE_API_KEY" in str(exc)
            or "TAVILY_API_KEY" in str(exc)
            or "TUSHARE_TOKEN" in str(exc)
            or "TUSHARE_API_KEY" in str(exc)
        )
    )


def _format_vendor_unavailable_message(
    method: str,
    errors: list[tuple[str, Exception]],
) -> str:
    details = "; ".join(
        f"{vendor}: {_summarize_vendor_error(exc)}" for vendor, exc in errors
    )
    return (
        f"Data unavailable for '{method}'. All configured data vendors failed: {details}. "
        "Try again later or configure a working fallback data vendor."
    )


def _summarize_vendor_error(exc: Exception) -> str:
    if isinstance(exc, (ChinaDataUnavailableError, DataUnavailableError)):
        return str(exc)
    if isinstance(exc, TavilyUnavailableError):
        return str(exc)
    if isinstance(exc, YFRateLimitError):
        return "rate limited by Yahoo Finance"
    if isinstance(exc, AlphaVantageRateLimitError):
        return "rate limited by Alpha Vantage"
    return str(exc)
