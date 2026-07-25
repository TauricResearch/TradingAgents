"""News curation: extraction, dedup, staleness, relevance marking, formatting.

Extracted from ``interface.py`` to keep the routing core focused on vendor
selection. These functions turn raw vendor news results into a single
source-labeled, deduplicated, relevance-marked package for downstream agents.

The module depends only on the target-ticker context, ticker normalization,
the news-consistency/credibility helpers, and config - it never imports the
routing core, so there is no circular dependency. ``_summarize_vendor_error``
stays in ``interface.py`` (it classifies vendor exception types); the news-side
wrapper here reaches it via a function-local import.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from .config import get_config
from .consistency import attach_cross_source_info, create_llm_from_config, cross_source_summary
from .credibility import attach_credibility, credibility_summary
from .target_context import get_target_ticker
from .ticker_utils import normalize_ticker_symbol, to_akshare_symbol


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


def _summarize_news_result(result: Any) -> str:
    count = len(_extract_news_items("unknown", result))
    return f"返回 {count} 条新闻"


def _summarize_vendor_error_for_news(err: Exception | str) -> str:
    if not isinstance(err, Exception):
        return str(err)
    # Function-local import: _summarize_vendor_error classifies vendor exception
    # types and lives in interface.py (routing core). Importing it at module level
    # would create a circular dependency.
    from .interface import _summarize_vendor_error

    return _summarize_vendor_error(err)


def _mark_news_relevance(items: list[dict[str, Any]]) -> int:
    """Soft-mark news items that do not mention the target ticker or company.

    Uses the run's target ticker (from the contextvar set at run start) and
    its resolved company name. Recall-first: any case-insensitive substring
    mention of a ticker form or the company name counts as relevant, so a
    genuinely relevant item is never falsely flagged. Items are not dropped -
    low-relevance ones are tagged so the downstream agent can weigh them
    accordingly. Returns the count of low-relevance items.

    When no target ticker is set (bare states, tests), no marking is applied.
    """
    target = get_target_ticker()
    if target is None:
        return 0
    target_ticker = target.ticker
    company_name = target.company_name
    low_count = 0
    for item in items:
        if _is_relevant_news_item(item, target_ticker, company_name):
            item["relevance"] = "high"
        else:
            item["relevance"] = "low"
            low_count += 1
    return low_count


def _company_short_form(company_name: str) -> str:
    """Return a common abbreviation of the company name for recall-first matching.

    English names with spaces use the first token (``"Apple"`` from
    ``"Apple Inc."``). Chinese names (no spaces, non-ASCII) use the last two
    characters as a typical abbreviation (``"茅台"`` from ``"贵州茅台"``). This
    may over-match (e.g. ``"银行"`` from ``"工商银行"``), which is acceptable
    because the relevance filter is recall-first: a genuinely relevant item
    must never be falsely flagged as low-relevance.
    """
    tokens = company_name.split()
    if len(tokens) > 1:
        return tokens[0].lower()
    if any(ord(ch) > 127 for ch in company_name) and len(company_name) >= 2:
        return company_name[-2:].lower()
    return ""


def _is_relevant_news_item(
    item: dict[str, Any],
    target_ticker: str,
    company_name: str | None,
) -> bool:
    """Return True when the item mentions the target ticker or company name.

    Recall-first matching against title + content. Ticker forms cover the
    bare code, the suffixed form, and the normalized form so ``600519``,
    ``600519.SH`` and ``600519.SS`` all match. Company matching tries the
    full name then a short form so items using a common abbreviation (e.g.
    ``"茅台"`` for ``"贵州茅台"``) are not falsely flagged. Matching is
    case-insensitive substring; an empty item body is treated as relevant
    (let the LLM judge) so it is not penalized for a missing content field.
    """
    text = " ".join(
        [str(item.get("title") or ""), str(item.get("content") or "")]
    ).lower()
    if not text.strip():
        return True

    ticker_forms: set[str] = set()
    for form in (
        target_ticker,
        to_akshare_symbol(target_ticker),
        normalize_ticker_symbol(target_ticker),
    ):
        if form:
            ticker_forms.add(form.lower())
    for form in ticker_forms:
        if form and form in text:
            return True

    if company_name:
        name_lower = company_name.lower()
        if name_lower and name_lower in text:
            return True
        short_form = _company_short_form(company_name)
        if short_form and short_form != name_lower and short_form in text:
            return True

    return False


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


_STALE_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d",
    "%Y%m%dT%H%M%S",
    "%Y%m%d",
    "%b %d, %Y",
    "%B %d, %Y",
)


def _parse_date_best_effort(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    cleaned = re.sub(r"\s+[A-Z]{2,4}$", "", text)
    for fmt in _STALE_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _filter_stale_items(
    items: list[dict[str, Any]], start_date: str, end_date: str
) -> tuple[list[dict[str, Any]], int]:
    """Remove items whose published date is outside the [start, end+1d] window.

    Returns (kept_items, stale_count).
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return items, 0

    end_inclusive = end + timedelta(days=1)
    kept = []
    stale_count = 0
    for item in items:
        # Respect pre-computed stale flag from Tavily
        if item.get("stale"):
            stale_count += 1
            continue
        pub_dt = _parse_date_best_effort(item.get("published", ""))
        if pub_dt is not None and (pub_dt < start or pub_dt >= end_inclusive):
            stale_count += 1
            continue
        kept.append(item)
    return kept, stale_count


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
    return re.sub(r"[^a-z0-9一-鿿]+", "", title)[:120]


def _format_curated_news(
    method: str,
    successes: list[tuple[str, Any]],
    errors: list[tuple[str, Exception | str]],
    start_date: str = "",
    end_date: str = "",
) -> str:
    cfg = get_config()
    max_items = int(cfg.get("news_curator_max_items", 10))
    items: list[dict[str, Any]] = []
    for vendor, result in successes:
        items.extend(_extract_news_items(vendor, result))

    # Timeliness: filter items whose published date is outside the query window
    stale_count = 0
    if start_date and end_date:
        items, stale_count = _filter_stale_items(items, start_date, end_date)

    # Cross-source consistency detection (before dedup to capture multi-source events)
    if len(successes) >= 2:
        llm = create_llm_from_config()
        attach_cross_source_info(items, llm)
    curated = _dedupe_news_items(items)[:max_items]
    attach_credibility(curated)
    cred_summary = credibility_summary(curated)
    cs_summary = cross_source_summary(curated) if len(successes) >= 2 else {"confirmed": 0, "single_source": 0}
    # Relevance marking (recall-first): soft-mark items that do not mention the
    # target ticker or company name, so they stay available but are flagged for
    # the downstream agent rather than silently mixed into target analysis.
    low_relevance_count = _mark_news_relevance(curated)
    sections = [
        "## Curated News Package",
        f"Method: `{method}`",
        "Sources used: " + ", ".join(vendor for vendor, _ in successes),
        f"Credibility: {cred_summary['high']} high, {cred_summary['medium']} medium, {cred_summary['low']} low",
        f"Cross-source: {cs_summary['confirmed']} confirmed by multiple sources, {cs_summary['single_source']} single-source only",
    ]
    if stale_count:
        sections.append(f"Timeliness: {stale_count} item(s) filtered as outside the {start_date}~{end_date} window.")
    if low_relevance_count:
        sections.append(
            f"Relevance: {low_relevance_count} item(s) marked low-relevance "
            f"(target ticker/company not detected in the item)."
        )

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
        credibility = item.get("credibility", "low")
        cs_tag = item.get("cross_source_tag", "")
        cs_part = f", {cs_tag}" if cs_tag else ""
        relevance = item.get("relevance")
        relevance_part = f", relevance: {relevance}" if relevance == "low" else ""
        body = [f"### {idx}. {title} (source: {source}, publisher: {publisher}{score_part}, credibility: {credibility}{cs_part}{relevance_part})"]
        if item.get("published"):
            body.append(f"Published: {item['published']}")
        if item.get("content"):
            body.append(str(item["content"]).strip())
        if item.get("url"):
            body.append(f"Link: {item['url']}")
        sections.append("\n".join(body))

    return "\n\n".join(sections)
