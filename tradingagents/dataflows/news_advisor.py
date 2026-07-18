"""LLM-based news coverage advisor.

Reviews curated news items and recommends whether additional search is needed,
with targeted queries to fill specific coverage gaps.  Implements the
*Reflection* pattern from Agentic RAG: the agent critiques its own output
and decides what to search next.

When no LLM is available, falls back to rule-based gap analysis.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from tradingagents.observability.provenance import direct_data_scope

from .config import get_config
from .consistency import create_llm_from_config
from .ticker_utils import is_a_share_ticker

logger = logging.getLogger(__name__)


@dataclass
class NewsAdvisorResult:
    """Structured recommendation from the news analysis agent."""

    should_enrich: bool
    queries: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""
    gaps: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_news_coverage(
    items: list[dict[str, Any]],
    profile: dict[str, Any],
    llm: Any | None = None,
) -> NewsAdvisorResult:
    """Analyze news coverage and recommend whether to search for more.

    Parameters
    ----------
    items : list[dict]
        Current curated news items (title, content, source, credibility, etc.)
    profile : dict
        Canonical company profile (ticker, name, full_name, industry, etc.)
    llm : optional
        LLM instance for semantic gap analysis.  Falls back to rule-based
        analysis when ``None``.

    Returns
    -------
    NewsAdvisorResult
        Contains ``should_enrich``, ``queries`` (Tavily-compatible search specs),
        ``reasoning``, and ``gaps``.
    """
    cfg = get_config()
    if not cfg.get("news_advisor_enabled", True):
        return NewsAdvisorResult(should_enrich=False, reasoning="Advisor disabled by config.")

    # Try LLM-based analysis first
    if llm is None:
        llm = create_llm_from_config()

    if llm is not None:
        try:
            return _analyze_via_llm(items, profile, llm)
        except Exception as exc:
            logger.warning("LLM news advisor failed, falling back to rules: %s", exc)

    return _analyze_via_rules(items, profile)


# ---------------------------------------------------------------------------
# LLM-based analysis (Reflection pattern)
# ---------------------------------------------------------------------------

_ADVISOR_PROMPT_TEMPLATE = """\
You are a financial news coverage analyst. Given a company profile and a list of \
news headlines that have been collected, your job is to:

1. Identify what IMPORTANT aspects of the company are NOT covered by the current news.
2. Decide if the gaps are significant enough to warrant additional searching.
3. If yes, generate targeted search queries (max 3) to fill the gaps.

Company: {name} ({ticker})
Industry: {industry}
Full name: {full_name}

Current news headlines ({n_items} items):
{headlines}

Respond in this exact JSON format (no markdown fences):
{{
  "should_enrich": true/false,
  "gaps": ["gap 1 description", "gap 2 description"],
  "reasoning": "one sentence explaining the decision",
  "queries": [
    {{"query": "search query text", "include_domains": [], "include_raw_content": false}}
  ]
}}

Important:
- Only suggest enrichment if there are SIGNIFICANT gaps (e.g., no earnings/financial news \
for a company that just reported, no industry context, missing key announcements).
- If the current coverage is adequate, set "should_enrich" to false.
- Queries should be specific and likely to find the missing information.
- For A-share stocks, include Chinese queries. For US stocks, use English.
- Max 3 queries. Quality over quantity.
"""


def _analyze_via_llm(
    items: list[dict[str, Any]],
    profile: dict[str, Any],
    llm: Any,
) -> NewsAdvisorResult:
    """Use LLM to analyze coverage gaps and generate targeted queries."""
    headlines = _format_headlines(items)
    prompt = _ADVISOR_PROMPT_TEMPLATE.format(
        name=profile.get("name", "Unknown"),
        ticker=profile.get("ticker", ""),
        industry=profile.get("industry", "Unknown"),
        full_name=profile.get("full_name", profile.get("name", "Unknown")),
        n_items=len(items),
        headlines=headlines,
    )

    with direct_data_scope("evidence.news_advisor"):
        response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    return _parse_advisor_response(content)


def _format_headlines(items: list[dict[str, Any]], max_items: int = 20) -> str:
    """Format items as a concise numbered list for the LLM prompt."""
    lines = []
    for idx, item in enumerate(items[:max_items], start=1):
        title = (item.get("title") or "Untitled").replace("\n", " ")[:100]
        source = item.get("source", "unknown")
        credibility = item.get("credibility", "low")
        lines.append(f"{idx}. [{source}/{credibility}] {title}")
    return "\n".join(lines) if lines else "(no news items)"


def _parse_advisor_response(text: str) -> NewsAdvisorResult:
    """Parse the LLM JSON response into a NewsAdvisorResult."""
    # Try to extract JSON from possible markdown code fences
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in advisor response: {text[:200]}")

    data = json.loads(match.group(0))

    should_enrich = bool(data.get("should_enrich", False))
    gaps = [str(g) for g in (data.get("gaps") or []) if g]
    reasoning = str(data.get("reasoning") or "")
    queries = _validate_queries(data.get("queries") or [])

    return NewsAdvisorResult(
        should_enrich=should_enrich,
        queries=queries,
        reasoning=reasoning,
        gaps=gaps,
    )


def _validate_queries(raw_queries: list[Any]) -> list[dict[str, Any]]:
    """Validate and normalize query dicts to match Tavily payload format."""
    validated = []
    for q in raw_queries[:3]:
        if not isinstance(q, dict):
            continue
        query_text = str(q.get("query") or "").strip()[:380]
        if not query_text:
            continue
        validated.append({
            "query": query_text,
            "include_domains": list(q.get("include_domains") or []),
            "include_raw_content": bool(q.get("include_raw_content", False)),
        })
    return validated


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

# Coverage dimensions and their required evidence
_COVERAGE_DIMENSIONS = {
    "earnings": {
        "keywords": ["earnings", "revenue", "profit", "业绩", "营收", "利润", "季报", "年报", "财报"],
        "weight": 2,
    },
    "announcements": {
        "keywords": ["announcement", "filing", "disclosure", "公告", "披露", "通知"],
        "weight": 1.5,
    },
    "industry": {
        "keywords": ["industry", "sector", "market", "competition", "行业", "市场", "竞争", "赛道"],
        "weight": 1,
    },
    "management": {
        "keywords": ["CEO", "CFO", "management", "executive", "管理层", "高管", "董事"],
        "weight": 0.5,
    },
}


def _analyze_via_rules(
    items: list[dict[str, Any]],
    profile: dict[str, Any],
) -> NewsAdvisorResult:
    """Rule-based gap analysis when no LLM is available."""
    if not items:
        return NewsAdvisorResult(
            should_enrich=True,
            reasoning="No news items found — need basic coverage.",
            gaps=["no news items at all"],
            queries=_fallback_queries(profile, "basic coverage"),
        )

    # Combine all text for keyword matching
    combined_text = " ".join(
        str(item.get("title", "")) + " " + str(item.get("content", ""))
        for item in items
    ).lower()

    gaps = []
    for dimension, spec in _COVERAGE_DIMENSIONS.items():
        keyword_hits = sum(1 for kw in spec["keywords"] if kw in combined_text)
        if keyword_hits == 0:
            gaps.append(f"missing {dimension} coverage")

    if not gaps:
        return NewsAdvisorResult(
            should_enrich=False,
            reasoning="All coverage dimensions adequately represented.",
        )

    # Only enrich if there are high-priority gaps
    high_priority_gaps = [g for g in gaps if "earnings" in g or "announcements" in g]
    if not high_priority_gaps:
        return NewsAdvisorResult(
            should_enrich=False,
            reasoning=f"Minor gaps ({', '.join(gaps)}) but sufficient for analysis.",
            gaps=gaps,
        )

    return NewsAdvisorResult(
        should_enrich=True,
        reasoning=f"Significant gaps: {', '.join(high_priority_gaps)}.",
        gaps=high_priority_gaps,
        queries=_fallback_queries(profile, ", ".join(high_priority_gaps)),
    )


def _fallback_queries(profile: dict[str, Any], gap_desc: str) -> list[dict[str, Any]]:
    """Generate fallback search queries based on profile and gap description."""
    ticker = str(profile.get("ticker") or "")
    name = str(profile.get("name") or "")
    full_name = str(profile.get("full_name") or name)

    if is_a_share_ticker(ticker):
        return [
            {
                "query": f"{ticker} {name} 公告 业绩 新闻",
                "include_domains": [],
                "include_raw_content": False,
            },
            {
                "query": f"{full_name} {ticker} 巨潮资讯 深交所 公告",
                "include_domains": ["cninfo.com.cn", "szse.cn"],
                "include_raw_content": True,
            },
        ]

    return [
        {
            "query": f"{ticker} {name} earnings news press release",
            "include_domains": [],
            "include_raw_content": False,
        },
        {
            "query": f"{full_name} SEC filing investor relations",
            "include_domains": ["sec.gov", "prnewswire.com", "businesswire.com"],
            "include_raw_content": True,
        },
    ]
