"""Evidence sufficiency checks and enrichment before downstream debate."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta
from enum import Enum
from functools import lru_cache
from typing import Any, Iterable
from urllib.parse import urlparse

import pandas as pd
import requests

from .config import get_config
from .ticker_utils import (
    is_a_share_ticker,
    normalize_ticker_symbol,
    to_yfinance_symbol,
    to_tushare_symbol,
)


class EvidenceStatus(str, Enum):
    PASS = "PASS"
    NEEDS_ENRICHMENT = "NEEDS_ENRICHMENT"
    FAIL_STOP = "FAIL_STOP"


class EvidenceGateError(RuntimeError):
    """Raised when evidence is too weak or contradictory for downstream debate."""


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
OFFICIAL_A_SHARE_DOMAINS = ("cninfo.com.cn", "szse.cn", "sse.com.cn", "bse.cn")
WRONG_IDENTITY_HINTS = ("恒瑞医药", "安洁科技")


def evaluate_and_enrich_evidence(state: dict[str, Any]) -> dict[str, Any]:
    """Validate evidence quality and optionally enrich weak news context."""
    cfg = get_config()
    if not cfg.get("evidence_gate_enabled", True):
        return {
            "evidence_status": EvidenceStatus.PASS.value,
            "evidence_report": "Evidence gate disabled by configuration.",
        }

    ticker = normalize_ticker_symbol(str(state.get("company_of_interest") or ""))
    profile = _complete_profile(state.get("canonical_company_profile"), ticker)
    if is_a_share_ticker(ticker) and not profile.get("name"):
        return _fail_or_return(
            "无法解析 A 股 canonical company profile，不能安全进入后续讨论。",
            profile,
        )

    core_warning = _assert_no_core_data_warnings(state, profile)
    if core_warning:
        return core_warning

    original_items = _dedupe_news_items(
        _extract_news_items_from_reports(
            state.get("news_report", ""),
            state.get("sentiment_report", ""),
        )
    )
    assessment = _assess_news_items(original_items, profile)
    if assessment["status"] == EvidenceStatus.PASS:
        return {
            "canonical_company_profile": profile,
            "evidence_status": EvidenceStatus.PASS.value,
            "evidence_report": _format_evidence_report(profile, assessment, enrichment_rounds=0),
        }

    max_rounds = int(cfg.get("evidence_max_enrichment_rounds", 3))
    deadline = time.monotonic() + float(cfg.get("evidence_max_enrichment_seconds", 90))
    enriched_items = _run_tavily_enrichment(profile, str(state.get("trade_date") or ""), max_rounds, deadline)
    all_items = _dedupe_news_items([*original_items, *enriched_items])
    enriched_assessment = _assess_news_items(all_items, profile)

    if enriched_assessment["status"] == EvidenceStatus.PASS:
        evidence_report = _format_evidence_report(
            profile,
            enriched_assessment,
            enrichment_rounds=max_rounds,
        )
        return {
            "canonical_company_profile": profile,
            "evidence_status": EvidenceStatus.PASS.value,
            "evidence_report": evidence_report,
            "news_report": _format_evidence_news_package(profile, all_items, evidence_report),
        }

    reason = (
        f"Tavily 补充 {max_rounds} 轮后仍不足："
        f"{'; '.join(enriched_assessment['reasons']) or '未获得可用新闻证据'}。"
    )
    return _fail_or_return(reason, profile, assessment=enriched_assessment)


@lru_cache(maxsize=256)
def resolve_canonical_company_profile(ticker: str) -> dict[str, Any]:
    """Resolve a stable profile for the instrument, best-effort for prompts."""
    normalized = normalize_ticker_symbol(ticker)
    profile = {
        "ticker": normalized,
        "symbol": normalized.split(".", 1)[0],
        "ts_code": to_tushare_symbol(normalized) if is_a_share_ticker(normalized) else normalized,
        "name": "",
        "full_name": "",
        "industry": "",
        "exchange": _exchange_name(normalized),
    }
    if not is_a_share_ticker(normalized):
        return profile

    try:
        from .china_data import _get_tushare_pro

        pro = _get_tushare_pro()
        ts_code = profile["ts_code"]
        try:
            df = pro.stock_basic(
                ts_code=ts_code,
                fields="ts_code,symbol,name,fullname,area,industry,market,list_date,act_name,act_ent_type",
            )
        except TypeError:
            df = pro.stock_basic(ts_code=ts_code)
        if isinstance(df, pd.DataFrame) and not df.empty:
            row = df.iloc[0].to_dict()
            profile.update(
                {
                    "ticker": normalize_ticker_symbol(str(row.get("ts_code") or normalized)),
                    "symbol": str(row.get("symbol") or profile["symbol"]),
                    "ts_code": str(row.get("ts_code") or profile["ts_code"]),
                    "name": str(row.get("name") or ""),
                    "full_name": str(row.get("fullname") or row.get("full_name") or row.get("name") or ""),
                    "industry": str(row.get("industry") or ""),
                    "market": str(row.get("market") or ""),
                    "area": str(row.get("area") or ""),
                    "act_name": str(row.get("act_name") or ""),
                    "act_ent_type": str(row.get("act_ent_type") or ""),
                    "exchange": _exchange_name(str(row.get("ts_code") or normalized)),
                }
            )
    except Exception as exc:
        profile["resolution_error"] = str(exc)
    if not profile.get("name"):
        _apply_akshare_profile(profile)
    if not profile.get("name"):
        _apply_yfinance_profile(profile)
    return profile


def format_company_profile(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    parts = [
        f"canonical ticker: `{profile.get('ticker') or profile.get('ts_code')}`",
        f"company short name: `{profile.get('name') or 'unknown'}`",
    ]
    if profile.get("full_name"):
        parts.append(f"full company name: `{profile['full_name']}`")
    if profile.get("industry"):
        parts.append(f"industry: `{profile['industry']}`")
    if profile.get("exchange"):
        parts.append(f"exchange: `{profile['exchange']}`")
    return "Canonical company profile: " + "; ".join(parts) + "."


def _apply_akshare_profile(profile: dict[str, Any]) -> None:
    try:
        from .china_data import _import_optional

        ak = _import_optional("akshare", "pip install akshare")
        df = ak.stock_individual_info_em(symbol=str(profile.get("symbol") or ""))
        if not isinstance(df, pd.DataFrame) or df.empty:
            return
        rows = {
            str(row.get("item") or "").strip(): str(row.get("value") or "").strip()
            for row in df.to_dict("records")
        }
        if rows.get("股票简称"):
            profile["name"] = rows["股票简称"]
        if rows.get("行业"):
            profile["industry"] = rows["行业"]
        if rows.get("股票代码"):
            profile["symbol"] = rows["股票代码"].zfill(6)
            suffix = str(profile.get("ticker", "")).split(".")[-1]
            profile["ticker"] = normalize_ticker_symbol(f"{profile['symbol']}.{suffix}")
            profile["ts_code"] = to_tushare_symbol(str(profile["ticker"]))
            profile["exchange"] = _exchange_name(str(profile["ticker"]))
        profile["profile_source"] = "akshare"
    except Exception as exc:
        profile["akshare_resolution_error"] = str(exc)


def _apply_yfinance_profile(profile: dict[str, Any]) -> None:
    try:
        yf = __import__("yfinance")
        ticker = to_yfinance_symbol(str(profile.get("ticker") or profile.get("ts_code") or ""))
        if not ticker:
            return
        yf_ticker = yf.Ticker(ticker)
        get_info = getattr(yf_ticker, "get_info", None)
        info = get_info() if callable(get_info) else getattr(yf_ticker, "info", {})
        if not isinstance(info, dict) or not info:
            return
        info_symbol = str(info.get("symbol") or "").upper()
        if info_symbol and info_symbol != ticker.upper():
            profile["yfinance_resolution_error"] = (
                f"YFinance symbol mismatch: requested {ticker}, got {info_symbol}"
            )
            return

        short_name = _first_nonempty(
            info.get("shortName"),
            info.get("displayName"),
            info.get("longName"),
        )
        long_name = _first_nonempty(info.get("longName"), short_name)
        industry = _first_nonempty(info.get("industry"), info.get("sector"))
        if short_name:
            profile["name"] = short_name
        if long_name:
            profile["full_name"] = long_name
        if industry:
            profile["industry"] = industry
        if info.get("exchange"):
            profile["yfinance_exchange"] = str(info["exchange"])
        if info.get("fullExchangeName"):
            profile["yfinance_full_exchange_name"] = str(info["fullExchangeName"])
        profile["profile_source"] = "yfinance"
    except Exception as exc:
        profile["yfinance_resolution_error"] = str(exc)


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() != "none":
            return text
    return ""


def _complete_profile(profile: Any, ticker: str) -> dict[str, Any]:
    if isinstance(profile, dict) and profile.get("name"):
        completed = dict(profile)
        completed.setdefault("ticker", normalize_ticker_symbol(ticker))
        completed.setdefault("symbol", str(completed["ticker"]).split(".", 1)[0])
        completed.setdefault("ts_code", to_tushare_symbol(str(completed["ticker"])))
        completed.setdefault("exchange", _exchange_name(str(completed["ticker"])))
        return completed
    return resolve_canonical_company_profile(ticker)


def _assert_no_core_data_warnings(state: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any] | None:
    text = "\n\n".join(
        str(state.get(key) or "")
        for key in ("market_report", "fundamentals_report")
    )
    warning_patterns = (
        "Supplemental source: unavailable",
        "Warning: Yahoo Finance",
        "暂未获取",
        "未获取到完整",
        "no usable financial statement",
        "Data unavailable",
    )
    hits = [pattern for pattern in warning_patterns if pattern.lower() in text.lower()]
    if hits:
        return _fail_or_return(
            "股票或财务核心数据覆盖不足，已触发证据门控："
            + ", ".join(hits),
            profile,
        )
    return None


def _extract_news_items_from_reports(*reports: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for report in reports:
        text = str(report or "").strip()
        if not text or text.lower().startswith("no curated news found"):
            continue
        blocks = re.split(r"\n(?=###\s+)", text)
        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines or not lines[0].startswith("###"):
                continue
            title = re.sub(r"^###\s+\d*\.?\s*", "", lines[0]).strip()
            url = ""
            content_lines = []
            publisher = ""
            published = ""
            for line in lines[1:]:
                lower = line.lower()
                if lower.startswith("link:"):
                    url = line.split(":", 1)[1].strip()
                elif lower.startswith("published:"):
                    published = line.split(":", 1)[1].strip()
                else:
                    content_lines.append(line)
            match = re.search(r"publisher:\s*([^,)]+)", title, flags=re.IGNORECASE)
            if match:
                publisher = match.group(1).strip()
            items.append(
                {
                    "title": title,
                    "url": url,
                    "content": " ".join(content_lines),
                    "publisher": publisher,
                    "published": published,
                    "source": "report",
                }
            )
    return items


def _assess_news_items(items: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    cfg = get_config()
    wrong_hits = _find_wrong_identity_hits(items, profile)
    if wrong_hits:
        return {
            "status": EvidenceStatus.FAIL_STOP,
            "reasons": ["身份冲突：" + ", ".join(sorted(wrong_hits))],
            "items": items,
            "company_count": 0,
            "mixed_count": 0,
            "low_coverage": False,
        }

    company_items = [item for item in items if _is_company_relevant(item, profile)]
    official_items = [item for item in items if _is_official_item(item)]
    industry_items = [item for item in items if _is_industry_relevant(item, profile)]
    mixed = _dedupe_news_items([*company_items, *official_items, *industry_items])

    min_company = int(cfg.get("news_min_company_items", 3))
    min_mixed = int(cfg.get("news_min_mixed_items", 5))
    if len(company_items) >= min_company:
        return _assessment_pass(items, company_items, mixed, low_coverage=False)
    if len(mixed) >= min_mixed and (company_items or official_items):
        return _assessment_pass(items, company_items, mixed, low_coverage=True)

    reasons = []
    if not items:
        reasons.append("未找到可解析新闻条目")
    if len(company_items) < min_company:
        reasons.append(f"公司直相关新闻 {len(company_items)}/{min_company}")
    if len(mixed) < min_mixed:
        reasons.append(f"混合证据 {len(mixed)}/{min_mixed}")
    return {
        "status": EvidenceStatus.NEEDS_ENRICHMENT,
        "reasons": reasons,
        "items": items,
        "company_count": len(company_items),
        "mixed_count": len(mixed),
        "low_coverage": False,
    }


def _assessment_pass(
    items: list[dict[str, Any]],
    company_items: list[dict[str, Any]],
    mixed_items: list[dict[str, Any]],
    *,
    low_coverage: bool,
) -> dict[str, Any]:
    return {
        "status": EvidenceStatus.PASS,
        "reasons": [],
        "items": items,
        "company_count": len(company_items),
        "mixed_count": len(mixed_items),
        "low_coverage": low_coverage,
    }


def _run_tavily_enrichment(
    profile: dict[str, Any],
    trade_date: str,
    rounds: int,
    deadline: float,
) -> list[dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []
    queries = _build_enrichment_queries(profile)
    if not queries:
        return []

    items: list[dict[str, Any]] = []
    for index, spec in enumerate(queries[:rounds], start=1):
        if time.monotonic() >= deadline:
            break
        payload = _build_tavily_payload(spec, trade_date)
        try:
            response = requests.post(
                TAVILY_SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=min(30, max(1, int(deadline - time.monotonic()))),
            )
            data = response.json()
        except Exception:
            continue
        _save_enrichment_raw_response(profile, trade_date, index, payload, data)
        if response.status_code >= 400:
            continue
        items.extend(_items_from_tavily_response(data))
    return _dedupe_news_items(items)


def _build_enrichment_queries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    ticker = str(profile.get("ticker") or profile.get("ts_code") or "")
    name = str(profile.get("name") or "")
    full_name = str(profile.get("full_name") or name)
    industry = str(profile.get("industry") or "")
    query_base = " ".join(part for part in (ticker, name) if part)
    return [
        {
            "query": f"{query_base} 公告 业绩 新闻 舆情",
            "include_domains": [],
            "include_raw_content": False,
        },
        {
            "query": f"{full_name} {ticker} 巨潮资讯 深交所 公告",
            "include_domains": ["cninfo.com.cn", "szse.cn"],
            "include_raw_content": True,
        },
        {
            "query": f"{name} {industry} 行业 订单 经营 市场 情绪",
            "include_domains": [],
            "include_raw_content": False,
        },
    ]


def _build_tavily_payload(spec: dict[str, Any], trade_date: str) -> dict[str, Any]:
    start_date, end_date = _date_window(trade_date)
    payload = {
        "query": spec["query"][:380],
        "search_depth": "advanced",
        "max_results": 10,
        "topic": "general",
        "start_date": start_date,
        "end_date": end_date,
        "include_raw_content": bool(spec.get("include_raw_content")),
        "include_answer": False,
        "include_images": False,
        "auto_parameters": False,
        "include_favicon": True,
    }
    if spec.get("include_domains"):
        payload["include_domains"] = spec["include_domains"]
    return payload


def _date_window(trade_date: str) -> tuple[str, str]:
    try:
        end = datetime.strptime(trade_date, "%Y-%m-%d")
    except Exception:
        end = datetime.now()
    start = end - timedelta(days=120)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _items_from_tavily_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for result in data.get("results") or []:
        if not isinstance(result, dict):
            continue
        items.append(
            {
                "title": result.get("title") or "Untitled",
                "url": result.get("url") or "",
                "content": result.get("raw_content") or result.get("content") or "",
                "published": result.get("published_date") or result.get("published_time") or "",
                "score": result.get("score"),
                "publisher": _publisher_from_url(result.get("url") or ""),
                "source": "tavily_enrichment",
            }
        )
    return items


def _dedupe_news_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen = set()
    for item in items:
        key = _news_dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(item))
    return deduped


def _news_dedupe_key(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip().lower()
    if url:
        parsed = urlparse(url)
        return f"{parsed.netloc}{parsed.path}".rstrip("/")
    title = str(item.get("title") or "").lower()
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title)
    return normalized[:160]


def _find_wrong_identity_hits(items: list[dict[str, Any]], profile: dict[str, Any]) -> set[str]:
    profile_names = _profile_name_aliases(profile)
    profile_codes = _profile_code_aliases(profile)
    hits: set[str] = set()

    for item in items:
        text = _item_text(item)
        item_codes = _explicit_stock_codes(text)
        wrong_codes = {code for code in item_codes if code not in profile_codes}
        item_source = str(item.get("source") or "")
        if item_source == "report":
            hits.update(wrong_codes)

        binds_profile_code = bool(item_codes & profile_codes)
        for name in WRONG_IDENTITY_HINTS:
            if name in text and not _is_profile_alias(name, profile_names):
                if item_source == "report" or binds_profile_code:
                    hits.add(name)

        hits.update(_wrong_names_bound_to_profile_code(text, profile, profile_names))
    return hits


def _profile_name_aliases(profile: dict[str, Any]) -> set[str]:
    aliases = {str(profile.get("name") or ""), str(profile.get("full_name") or "")}
    return {alias for alias in aliases if alias}


def _profile_code_aliases(profile: dict[str, Any]) -> set[str]:
    aliases = {
        str(profile.get("ticker") or "").upper(),
        str(profile.get("ts_code") or "").upper(),
        str(profile.get("symbol") or ""),
    }
    return {alias for alias in aliases if alias}


def _explicit_stock_codes(text: str) -> set[str]:
    hits = {match.group(0).upper() for match in re.finditer(r"(?<!\w)\d{6}\.(?:SZ|SH|SS|BJ)(?!\w)", text, re.IGNORECASE)}
    for match in re.finditer(r"(?:证券代码|股票代码|stock\s+code|ticker)[：:\s]*([0-9]{6})", text, re.IGNORECASE):
        hits.add(match.group(1))
    return hits


def _wrong_names_bound_to_profile_code(
    text: str,
    profile: dict[str, Any],
    profile_names: set[str],
) -> set[str]:
    hits: set[str] = set()
    code_tokens = [re.escape(code) for code in _profile_code_aliases(profile)]
    if not code_tokens:
        return hits
    code_pattern = "|".join(sorted(code_tokens, key=len, reverse=True))
    for match in re.finditer(rf"(?:{code_pattern})\s*[（(]\s*([\u4e00-\u9fffA-Za-z0-9&·-]{{2,24}})\s*[）)]", text):
        candidate = match.group(1).strip()
        if not candidate or _is_profile_alias(candidate, profile_names):
            continue
        if profile.get("profile_source") == "yfinance" and candidate not in WRONG_IDENTITY_HINTS:
            continue
        if candidate:
            hits.add(candidate)
    return hits


def _is_profile_alias(candidate: str, profile_names: set[str]) -> bool:
    return any(candidate in name or name in candidate for name in profile_names)


def _is_company_relevant(item: dict[str, Any], profile: dict[str, Any]) -> bool:
    text = _item_text(item)
    candidates = {
        str(profile.get("ticker") or ""),
        str(profile.get("ts_code") or ""),
        str(profile.get("symbol") or ""),
        str(profile.get("name") or ""),
        str(profile.get("full_name") or ""),
    }
    return any(candidate and candidate in text for candidate in candidates)


def _is_official_item(item: dict[str, Any]) -> bool:
    domain = urlparse(str(item.get("url") or "")).netloc.lower()
    return any(official in domain for official in OFFICIAL_A_SHARE_DOMAINS)


def _is_industry_relevant(item: dict[str, Any], profile: dict[str, Any]) -> bool:
    industry = str(profile.get("industry") or "")
    return bool(industry and industry in _item_text(item))


def _item_text(item: dict[str, Any]) -> str:
    return "\n".join(
        str(item.get(key) or "")
        for key in ("title", "content", "publisher", "url")
    )


def _format_evidence_report(
    profile: dict[str, Any],
    assessment: dict[str, Any],
    *,
    enrichment_rounds: int,
) -> str:
    status_line = "低覆盖通过" if assessment.get("low_coverage") else "通过"
    return "\n".join(
        [
            "## Evidence Steward Report",
            format_company_profile(profile),
            f"Status: {status_line}",
            f"Company evidence items: {assessment.get('company_count', 0)}",
            f"Mixed evidence items after deduplication: {assessment.get('mixed_count', 0)}",
            f"Tavily enrichment rounds used: {enrichment_rounds}",
            "Deduplication: URL query strings and repeated titles are collapsed before downstream context injection.",
        ]
    )


def _format_evidence_news_package(
    profile: dict[str, Any],
    items: list[dict[str, Any]],
    evidence_report: str,
) -> str:
    cfg = get_config()
    max_items = int(cfg.get("news_curator_max_items", 10))
    sections = [
        "## Evidence-Gated News Package",
        evidence_report,
        "The following items are deduplicated and identity-filtered before downstream debate.",
    ]
    for idx, item in enumerate(items[:max_items], start=1):
        sections.append(_format_item(idx, item, profile))
    return "\n\n".join(sections)


def _format_item(idx: int, item: dict[str, Any], profile: dict[str, Any]) -> str:
    title = str(item.get("title") or "Untitled").strip()
    publisher = str(item.get("publisher") or item.get("source") or "unknown").strip()
    parts = [f"### {idx}. {title} (publisher: {publisher})"]
    if item.get("published"):
        parts.append(f"Published: {item['published']}")
    content = str(item.get("content") or "").strip()
    if content:
        parts.append(content[:1200])
    if item.get("url"):
        parts.append(f"Link: {item['url']}")
    parts.append(f"Identity check: matched {profile.get('ticker')} / {profile.get('name')}.")
    return "\n".join(parts)


def _save_enrichment_raw_response(
    profile: dict[str, Any],
    trade_date: str,
    round_index: int,
    payload: dict[str, Any],
    data: dict[str, Any],
) -> None:
    try:
        from .tavily_news import _save_raw_response

        _save_raw_response(
            str(profile.get("ticker") or profile.get("symbol") or "UNKNOWN"),
            trade_date or datetime.now().strftime("%Y-%m-%d"),
            f"evidence_enrichment_round_{round_index}",
            payload,
            data,
        )
    except Exception:
        return


def _publisher_from_url(url: str) -> str:
    domain = urlparse(str(url or "")).netloc.lower()
    if "cninfo.com.cn" in domain:
        return "巨潮资讯"
    if "szse.cn" in domain:
        return "深交所"
    return domain or "unknown"


def _exchange_name(ticker: str) -> str:
    value = to_tushare_symbol(str(ticker or ""))
    if value.endswith(".SZ"):
        return "深圳证券交易所"
    if value.endswith(".SH") or value.endswith(".SS"):
        return "上海证券交易所"
    if value.endswith(".BJ"):
        return "北京证券交易所"
    return ""


def _fail_or_return(
    reason: str,
    profile: dict[str, Any],
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = get_config()
    report = "\n".join(
        [
            "## Evidence Steward Report",
            format_company_profile(profile),
            f"Status: {EvidenceStatus.FAIL_STOP.value}",
            f"Reason: {reason}",
        ]
    )
    if cfg.get("evidence_stop_on_fail", True):
        raise EvidenceGateError(f"{reason}\n\n{report}")
    return {
        "canonical_company_profile": profile,
        "evidence_status": EvidenceStatus.FAIL_STOP.value,
        "evidence_report": report,
    }
