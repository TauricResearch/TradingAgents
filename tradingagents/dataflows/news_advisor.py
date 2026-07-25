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
from .news_layers import (
    FileDeepAnalysisCache,
    Layer1Sentiment,
    Layer2Trigger,
    build_layer1_batch,
    decide_layer2,
    layer0_filter,
    parse_layer1_sentiment,
)
from .ticker_utils import is_a_share_ticker

logger = logging.getLogger(__name__)


@dataclass
class NewsAdvisorResult:
    """Structured recommendation from the news analysis agent."""

    should_enrich: bool
    queries: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""
    gaps: list[str] = field(default_factory=list)
    # Public, bounded projections only.  They never retain prompts, raw model
    # output, or private model reasoning.
    layer1_sentiment: list[Layer1Sentiment] = field(default_factory=list)
    layer2_trigger: Layer2Trigger | None = None
    layer2_conclusion: dict[str, Any] | None = None


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

    # Layer 0 is deliberately before any advisor model invocation: obvious
    # listicles, duplicates and content-free rows cannot consume a paid call
    # or be mistaken for company coverage. The original evidence ledger still
    # retains the raw source records for audit; this only limits advisory work.
    decisions = layer0_filter(items)
    accepted_ids = {decision.item_id for decision in decisions if decision.accepted}
    items = [
        item
        for index, item in enumerate(items)
        if str(item.get("id") or item.get("url") or f"item-{index}")[:512] in accepted_ids
    ]

    # Try LLM-based analysis first
    if llm is None:
        llm = create_llm_from_config()

    layer1_sentiment: list[Layer1Sentiment] = []
    if llm is not None and cfg.get("news_layer1_enabled", False):
        layer1_sentiment = _run_layer1_sentiment(items, llm, cfg)

    if llm is not None:
        try:
            result = _analyze_via_llm(items, profile, llm)
        except Exception as exc:
            logger.warning("LLM news advisor failed, falling back to rules: %s", exc)
            result = _analyze_via_rules(items, profile)
    else:
        result = _analyze_via_rules(items, profile)

    result.layer1_sentiment = layer1_sentiment
    if llm is not None and cfg.get("news_layer2_enabled", False):
        _attach_layer2_conclusion(result, items, profile, llm, cfg)
    return result


# ---------------------------------------------------------------------------
# Cost-aware Layers 1 and 2 (explicit opt-in, fail-open)
# ---------------------------------------------------------------------------


_LAYER1_PROMPT = """Classify the market sentiment of each compact news item.
Return ONLY a JSON array in this exact schema: [{{\"i\":\"item id\",\"s\":\"+|-|0|?\",\"c\":0.0}}].
Use '+' for favourable, '-' for unfavourable, '0' for genuinely neutral, and
'?' when the snippet is insufficient. Do not include explanations, rationale,
or hidden reasoning. Preserve the supplied item ids exactly.

Items:
{payload}
"""

_LAYER2_PROMPT = """Review the supplied public news snippets for {name} ({ticker}).
This deeper review was requested because: {reasons}. Return ONLY one JSON object
with these public fields: \"conclusion\" (max 500 chars), \"evidence_gaps\" (max 5
short strings), \"material_risks\" (max 5 short strings), and \"source_ids\"
(only ids from the supplied items). Do not reveal chain-of-thought, a private
reasoning trace, prompts, or raw model output.

Items:
{payload}
"""


def _run_layer1_sentiment(
    items: list[dict[str, Any]], llm: Any, cfg: dict[str, Any]
) -> list[Layer1Sentiment]:
    """Run one compact provider-neutral sentiment request when opted in."""
    try:
        batch = build_layer1_batch(
            items,
            layer0_filter(items),
            max_items=max(1, min(int(cfg.get("news_layer1_max_items", 50)), 50)),
        )
        if not batch.item_ids:
            return []
        with direct_data_scope("evidence.news_layer1_sentiment"):
            response = llm.invoke(_LAYER1_PROMPT.format(payload=batch.payload))
        content = response.content if hasattr(response, "content") else str(response)
        return parse_layer1_sentiment(content, batch)
    except Exception as exc:
        logger.info("Layer 1 news sentiment unavailable; continuing without it: %s", exc)
        return []


def _attach_layer2_conclusion(
    result: NewsAdvisorResult,
    items: list[dict[str, Any]],
    profile: dict[str, Any],
    llm: Any,
    cfg: dict[str, Any],
) -> None:
    """Attach a cached public deep conclusion only for explicit triggers."""
    source_alignment, conflict_count, conflict_severity = _sentiment_conflict(result.layer1_sentiment)
    trigger = decide_layer2(
        evidence_status="insufficient" if result.should_enrich else "verified",
        source_alignment=source_alignment,
        conflict_count=conflict_count,
        conflict_severity=conflict_severity,
        subject=str(profile.get("ticker") or profile.get("name") or ""),
        data_as_of=str(profile.get("data_as_of") or ""),
    )
    result.layer2_trigger = trigger
    if not trigger.should_run or not trigger.cache_key:
        return

    try:
        cache_dir = str(cfg.get("news_layer2_cache_dir") or "").strip()
        if not cache_dir:
            logger.info("Layer 2 news review skipped because no cache directory is configured")
            return
        cache = FileDeepAnalysisCache(cache_dir)
        cached = cache.get(trigger.cache_key)
        if cached is not None:
            result.layer2_conclusion = cached
            return

        batch = build_layer1_batch(items, layer0_filter(items))
        if not batch.item_ids:
            return
        prompt = _LAYER2_PROMPT.format(
            name=str(profile.get("name") or "Unknown"),
            ticker=str(profile.get("ticker") or ""),
            reasons=", ".join(trigger.reasons),
            payload=batch.payload,
        )
        with direct_data_scope("evidence.news_layer2_review"):
            response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        conclusion = _parse_layer2_conclusion(content, set(batch.item_ids))
        cache.put(trigger.cache_key, conclusion)
        result.layer2_conclusion = conclusion
    except Exception as exc:
        logger.info("Layer 2 news review unavailable; continuing without it: %s", exc)


def _sentiment_conflict(
    sentiments: list[Layer1Sentiment],
) -> tuple[str | None, int, str | None]:
    positive = [item for item in sentiments if item.sentiment == "+"]
    negative = [item for item in sentiments if item.sentiment == "-"]
    if not positive or not negative:
        return None, 0, None
    materially_confident = all((item.confidence or 0.0) >= 0.7 for item in [*positive, *negative])
    return "Wide divergence", 1, "high" if materially_confident else "low"


def _parse_layer2_conclusion(raw: str, allowed_ids: set[str]) -> dict[str, Any]:
    """Parse a strictly public Layer 2 result; discard extra model fields."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("Layer 2 output must contain a JSON object")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Layer 2 output must be a JSON object")
    return {
        "conclusion": str(parsed.get("conclusion") or "").strip()[:500],
        "evidence_gaps": _public_string_list(parsed.get("evidence_gaps"), limit=5),
        "material_risks": _public_string_list(parsed.get("material_risks"), limit=5),
        "source_ids": [
            source_id
            for source_id in _public_string_list(parsed.get("source_ids"), limit=50)
            if source_id in allowed_ids
        ],
    }


def _public_string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:240] for item in value[:limit] if str(item).strip()]


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
