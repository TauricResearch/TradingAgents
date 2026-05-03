"""Output validation utilities for detecting hallucinated or off-topic responses.

This module provides validation functions to check if agent outputs are actually
analyzing the provided data rather than hallucinating generic content.
"""

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.json_utils import extract_json
from tradingagents.agents.utils.llm_guard import invoke_with_timeout, resolve_timeout

logger = logging.getLogger(__name__)

_SCRATCHPAD_PHRASES = (
    "we need to",
    "we have limited data",
    "we can create",
    "let's extract",
    "let's craft",
    "we'll just use",
    "now produce final answer",
    "could format as",
)


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    reason: str
    code: str = "ok"


@dataclass(frozen=True)
class ExtractionResult:
    """Result of action extraction from text."""
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: Literal["high", "med", "low"]
    source: Literal["regex", "llm"]
    evidence_quote: str | None


class ActionExtractionError(Exception):
    """Raised when action extraction fails for all methods."""
    def __init__(self, text_excerpt: str, last_attempt: "ExtractionResult | None" = None):
        self.text_excerpt = text_excerpt
        self.last_attempt = last_attempt
        excerpt_display = text_excerpt[:300] if len(text_excerpt) > 300 else text_excerpt
        super().__init__(
            f"action_extraction_failed: could not determine BUY/SELL/HOLD from text "
            f"(first 300 chars): {excerpt_display!r}"
        )


class CandidateHandoffError(Exception):
    """Raised when candidate handoff validation fails."""
    def __init__(
        self,
        kind: Literal["unaccountable_drop", "all_extraction_failed"],
        n_in: int,
        n_out: int,
        per_ticker_status: dict[str, str],
    ):
        self.kind = kind
        self.n_in = n_in
        self.n_out = n_out
        self.per_ticker_status = per_ticker_status
        super().__init__(
            f"candidate_handoff_error kind={kind} n_in={n_in} n_out={n_out} "
            f"per_ticker={per_ticker_status}"
        )


CANONICAL_SOURCE_REGISTRY = {
    "finviz_smart_money_scanner": {
        "display_name": "Finviz Smart Money Scanner",
        "aliases": {
            "finviz smart money scanner",
            "finviz smart money",
            "finviz scanner",
            "smart money scanner",
            "finviz",
        },
    },
    "alpha_vantage": {
        "display_name": "Alpha Vantage",
        "aliases": {"alpha vantage"},
    },
    "yfinance": {
        "display_name": "yfinance",
        "aliases": {"yfinance", "yahoo finance"},
    },
    "sec_edgar": {
        "display_name": "SEC EDGAR",
        "aliases": {"sec edgar", "sec", "edgar"},
    },
    "sec_form_4": {
        "display_name": "SEC Form 4",
        "aliases": {"sec form 4", "form 4", "form 4 filing"},
    },
    "sec_form_13f": {
        "display_name": "SEC Form 13F",
        "aliases": {"sec form 13f", "form 13f", "form 13f filing"},
    },
    "reuters": {
        "display_name": "Reuters",
        "aliases": {"reuters"},
    },
    "bloomberg": {
        "display_name": "Bloomberg",
        "aliases": {"bloomberg"},
    },
    "cnbc": {
        "display_name": "CNBC",
        "aliases": {"cnbc"},
    },
    "wall_street_journal": {
        "display_name": "Wall Street Journal",
        "aliases": {"wall street journal", "wsj"},
    },
    "financial_times": {
        "display_name": "Financial Times",
        "aliases": {"financial times"},
    },
    "marketwatch": {
        "display_name": "MarketWatch",
        "aliases": {"marketwatch"},
    },
    "seeking_alpha": {
        "display_name": "Seeking Alpha",
        "aliases": {"seeking alpha"},
    },
    "barrons": {
        "display_name": "Barron's",
        "aliases": {"barron's", "barrons"},
    },
    "forbes": {
        "display_name": "Forbes",
        "aliases": {"forbes"},
    },
    "thestreet": {
        "display_name": "TheStreet",
        "aliases": {"thestreet", "the street"},
    },
    "motley_fool": {
        "display_name": "Motley Fool",
        "aliases": {"motley fool"},
    },
    "clarksons_platou": {
        "display_name": "Clarksons Platou Securities",
        "aliases": {
            "clarksons platou securities",
            "clarksons platou securities analyst report",
            "clarksons",
        },
    },
    "macro_scan": {
        "display_name": "Macro Scan",
        "aliases": {"macro scan", "scanner context"},
    },
}

SCANNER_CITATION_PATTERN = re.compile(
    r"\[Source:\s*Finviz Smart Money Scanner\s*\|\s*Scan Date:\s*(\d{4}-\d{2}-\d{2})\]",
    re.IGNORECASE,
)
EVIDENCE_ID_PATTERN = re.compile(r"\[Evidence ID:\s*([^\]]+)\]", re.IGNORECASE)
SCANNER_KEYWORDS = (
    "smart money",
    "unusual volume",
    "institutional flow",
    "flow signal",
    "scanner context",
    "insider buying",
)
_GENERIC_SOURCE_CANDIDATES = {
    "company",
    "the company",
    "management",
    "the management",
    "analyst",
    "analysts",
    "the analyst",
    "the analysts",
    "report",
    "the report",
    "reports",
    "the reports",
    "article",
    "the article",
    "articles",
    "the articles",
    "market",
    "the market",
    "market data",
    "investors",
    "the investors",
}


@dataclass(frozen=True)
class StructuredNewsValidationResult:
    is_valid: bool
    reason: str
    payload: dict[str, Any] | None = None
    code: str = "ok"


def infer_macro_regime_from_prefetched_report(macro_regime_report: str) -> str:
    """Infer a normalized macro regime from explicit pre-fetched macro text only."""
    text = str(macro_regime_report or "").strip().lower()
    if not text:
        return "unknown"
    # Prefer: match "regime" followed closely by the classification word.
    # This anchors to the regime *declaration* and avoids false positives like
    # "0 risk-off signals" appearing in the signal-count line of a RISK-ON report.
    match = re.search(r"\bregime\b.{0,60}?(risk-on|risk on|risk-off|risk off|transition)\b", text)
    if match:
        token = match.group(1)
        if "off" in token:
            return "risk_off"
        if "on" in token:
            return "risk_on"
        return "transition"
    # Fallback: count all occurrences and take the majority. Handles compact formats
    # (e.g. "## Risk-On") that omit the word "regime" entirely.
    risk_on_count = len(re.findall(r"risk[-\s]on", text))
    risk_off_count = len(re.findall(r"risk[-\s]off", text))
    if risk_on_count > risk_off_count:
        return "risk_on"
    if risk_off_count > risk_on_count:
        return "risk_off"
    if "transition" in text:
        return "transition"
    return "unknown"


def _count_summary_table_rows(report: str) -> int:
    rows = 0
    for line in str(report or "").splitlines():
        stripped = line.strip()
        if "|" not in stripped:
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            continue
        rows += 1
    return rows


def _extract_key_levels(report: str, *, max_levels: int = 3) -> list[str]:
    matches = re.findall(r"\$[0-9]+(?:\.[0-9]{1,2})?", str(report or ""))
    deduped: list[str] = []
    for value in matches:
        if value in deduped:
            continue
        deduped.append(value)
        if len(deduped) >= max_levels:
            break
    return deduped


def _extract_current_price_from_report(report: str) -> str | None:
    """Extract the current/live price from a market analyst report prose.

    Patterns are ordered most-specific to least-specific. Pattern 3 has a
    negative lookbehind to avoid matching "target price at", "support price at",
    "strike price at", etc. Returns None (with a warning) when no pattern matches.
    """
    import logging as _logging

    _logger = _logging.getLogger(__name__)

    patterns = [
        r"current\s+price\s+(?:of\s+)?\$([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"currently\s+trading\s+at\s+\$([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?:closed?|last|open(?:ing)?|traded?)\s+(?:at|@)\s+\$([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?:shares?\s+)?(?:trading|trades?)\s+(?:near|around|at)\s+\$([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"(?<!target\s)(?<!support\s)(?<!strike\s)(?<!resistance\s)price\s+(?:is\s+)?at\s+\$([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    ]
    report_str = str(report or "")
    for pat in patterns:
        m = re.search(pat, report_str, re.IGNORECASE)
        if m:
            token = m.group(1).replace(",", "")
            try:
                val = float(token)
                if val > 0:
                    return f"${val:.2f}"
            except ValueError:
                continue
    _logger.warning(
        "output_validation: could not extract current price from market report — "
        "drift guardrail will be skipped. Report excerpt: %.200s",
        report_str,
    )
    return None


def build_market_report_structured(
    *,
    ticker: str,
    as_of_date: str,
    market_report: str,
    macro_regime_report: str,
    contract_version: str = "market_summary_v1",
    is_timeout_fallback: bool = False,
) -> dict[str, Any]:
    """Build a compact canonical contract for market node output."""
    report = str(market_report or "").strip()
    if is_timeout_fallback:
        status = "timeout_fallback"
        abort_reason = ""
    elif not report:
        status = "empty"
        abort_reason = ""
    else:
        status = "completed"
        abort_reason = ""

    bullet_count = len(re.findall(r"(?m)^\s*[-*]\s+", report))
    numeric_mentions = len(
        re.findall(r"\$[0-9]|[0-9]+(?:\.[0-9]+)?%|[0-9]+(?:\.[0-9]+)?\s*bps", report, re.IGNORECASE)
    )
    summary_table_rows = _count_summary_table_rows(report)

    return {
        "ticker": str(ticker or "").strip().upper(),
        "as_of_date": str(as_of_date or "").strip(),
        "status": status,
        "contract_version": contract_version,
        "abort_reason": abort_reason,
        "claim_count": bullet_count,
        "macro_regime": infer_macro_regime_from_prefetched_report(macro_regime_report),
        "macro_regime_report_present": bool(str(macro_regime_report or "").strip()),
        "current_price": _extract_current_price_from_report(report),
        "key_levels": _extract_key_levels(report),
        "key_metrics": {
            "numeric_mentions": numeric_mentions,
            "summary_table_rows": summary_table_rows,
            "report_char_count": len(report),
        },
    }


def _compact_text(text: str, *, max_chars: int = 200) -> str:
    line = " ".join(str(text or "").strip().split())
    if not line:
        return ""
    if len(line) <= max_chars:
        return line
    return line[: max_chars - 3].rstrip() + "..."


def _summarize_prefetched_sections(
    prefetched_sections: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    if not isinstance(prefetched_sections, dict):
        return sections

    for label, raw_value in prefetched_sections.items():
        content = str(raw_value or "").strip()
        sections[str(label)] = {
            "present": bool(content),
            "error": content.startswith("[Error fetching") or content.startswith("[Error]"),
            "char_count": len(content),
            "excerpt": _compact_text(content, max_chars=180),
        }
    return sections


def build_fundamentals_report_structured(
    *,
    ticker: str,
    as_of_date: str,
    fundamentals_report: str,
    macro_regime_report: str,
    prefetched_sections: dict[str, Any] | None = None,
    contract_version: str = "fundamentals_summary_v1",
    is_timeout_fallback: bool = False,
) -> dict[str, Any]:
    """Build a compact canonical contract for fundamentals node output."""
    report = str(fundamentals_report or "").strip()
    timeout_detected = is_timeout_fallback or "timed out after" in report.lower()
    if timeout_detected:
        status = "timeout_fallback"
        abort_reason = ""
    elif not report:
        status = "empty"
        abort_reason = ""
    else:
        status = "completed"
        abort_reason = ""

    bullet_count = len(re.findall(r"(?m)^\s*[-*]\s+", report))
    numeric_mentions = len(
        re.findall(r"\$[0-9]|[0-9]+(?:\.[0-9]+)?%|[0-9]+(?:\.[0-9]+)?\s*bps", report, re.IGNORECASE)
    )
    summary_table_rows = _count_summary_table_rows(report)
    sections = _summarize_prefetched_sections(prefetched_sections)
    present_sections = [label for label, meta in sections.items() if meta.get("present")]
    error_sections = [label for label, meta in sections.items() if meta.get("error")]

    return {
        "ticker": str(ticker or "").strip().upper(),
        "as_of_date": str(as_of_date or "").strip(),
        "status": status,
        "contract_version": contract_version,
        "abort_reason": abort_reason,
        "bullet_count": bullet_count,
        "macro_regime": infer_macro_regime_from_prefetched_report(macro_regime_report),
        "macro_regime_report_present": bool(str(macro_regime_report or "").strip()),
        "prefetch": {
            "section_count": len(sections),
            "present_sections": present_sections,
            "error_sections": error_sections,
            "sections": sections,
        },
        "key_metrics": {
            "numeric_mentions": numeric_mentions,
            "summary_table_rows": summary_table_rows,
            "report_char_count": len(report),
        },
        "report_excerpt": _compact_text(report, max_chars=260),
    }


def render_fundamentals_report_structured(payload: dict[str, Any]) -> str:
    """Render fundamentals structured data into a deterministic markdown fallback."""
    ticker_upper = str(payload.get("ticker") or "").strip().upper()
    report_title = (
        f"{ticker_upper} Fundamentals Analysis" if ticker_upper else "Fundamentals Analysis"
    )
    key_metrics = payload.get("key_metrics") or {}
    prefetch = payload.get("prefetch") or {}
    sections = prefetch.get("sections") if isinstance(prefetch, dict) else {}
    present_sections = prefetch.get("present_sections") if isinstance(prefetch, dict) else []
    error_sections = prefetch.get("error_sections") if isinstance(prefetch, dict) else []

    lines = [
        report_title,
        "",
        f"- Ticker: {ticker_upper or 'N/A'}",
        f"- As of Date: {payload.get('as_of_date') or 'N/A'}",
        f"- Status: {payload.get('status') or 'unknown'}",
        f"- Contract Version: {payload.get('contract_version') or 'unknown'}",
        f"- Macro Regime: {payload.get('macro_regime') or 'unknown'}",
        f"- Macro Regime Present: {bool(payload.get('macro_regime_report_present'))}",
        f"- Bullet Count: {payload.get('bullet_count', 0)}",
        f"- Numeric Mentions: {key_metrics.get('numeric_mentions', 0)}",
        f"- Summary Table Rows: {key_metrics.get('summary_table_rows', 0)}",
    ]

    if payload.get("report_excerpt"):
        lines.extend(["", "### Report Excerpt", "", str(payload["report_excerpt"])])

    if isinstance(sections, dict) and sections:
        lines.extend(["", "### Prefetched Sections"])
        for label, meta in sections.items():
            if not isinstance(meta, dict):
                continue
            status = "present" if meta.get("present") else "missing"
            if meta.get("error"):
                status = "error"
            excerpt = str(meta.get("excerpt") or "").strip()
            char_count = meta.get("char_count", 0)
            lines.append(f"- {label}: {status} ({char_count} chars)")
            if excerpt:
                lines.append(f"  - {excerpt}")

    if present_sections:
        lines.extend(
            ["", f"- Present Sections: {', '.join(str(item) for item in present_sections)}"]
        )
    if error_sections:
        lines.extend(["", f"- Error Sections: {', '.join(str(item) for item in error_sections)}"])

    return "\n".join(lines).strip()


def output_contains_scratchpad(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().split()).lower()
    if not normalized:
        return False
    return any(phrase in normalized for phrase in _SCRATCHPAD_PHRASES)


def build_research_manager_fallback(state: AgentState) -> str:
    ticker = str(state.get("company_of_interest") or "").strip().upper()
    news_structured = state.get("news_report_structured") or {}
    fundamentals_structured = state.get("fundamentals_report_structured") or {}
    market_structured = state.get("market_report_structured") or {}

    lines: list[str] = []

    # Check news status and usability before iterating claims
    news_status = str(news_structured.get("status") or "").strip()
    key_metrics = news_structured.get("key_metrics") or {}
    claim_count = key_metrics.get("claim_count", 0) if isinstance(key_metrics, dict) else 0
    news_has_usable_evidence = news_status == "completed" and claim_count > 0

    if news_has_usable_evidence:
        # Gate news claim iteration behind usable evidence check
        for claim in (news_structured.get("claims") or [])[:3]:
            if not isinstance(claim, dict):
                continue
            claim_text = str(claim.get("claim") or "").strip()
            source = str(claim.get("source") or "").strip()
            published_at = str(claim.get("published_at") or "").strip()
            if claim_text:
                provenance = " ".join(part for part in (source, published_at) if part)
                lines.append(
                    f"- Bull: {claim_text}" + (f" [{provenance}]" if provenance else "") + " (MED)"
                )
    else:
        # News structured contract is not usable evidence
        if news_status:
            lines.append(f"- Bear: News structured contract has status '{news_status}' (MED)")

    key_levels = market_structured.get("key_levels") or []
    if isinstance(key_levels, list) and key_levels:
        lines.append(
            f"- Bull: Market context includes {len(key_levels)} validated price levels ({', '.join(str(v) for v in key_levels[:3])}) (LOW)"
        )

    key_metrics = fundamentals_structured.get("key_metrics") or {}
    if fundamentals_structured.get("status") == "timeout_fallback":
        lines.append(
            "- Bear: Fundamentals analysis timed out after 60s, leaving quantitative coverage incomplete (HIGH)"
        )
    if key_metrics.get("numeric_mentions", 0) == 0:
        lines.append("- Bear: Fundamentals structured contract reports 0 numeric mentions (HIGH)")
    macro_regime = str(fundamentals_structured.get("macro_regime") or "").strip().lower()
    if macro_regime in {"", "unknown"}:
        lines.append(
            "- Bear: Fundamentals structured contract classifies macro regime as unknown (MED)"
        )

    has_high_bear = any("(HIGH)" in line and line.startswith("- Bear:") for line in lines)
    has_bull = any(line.startswith("- Bull:") for line in lines)
    recommendation = "HOLD" if has_high_bear else ("BUY" if has_bull else "HOLD")
    rationale = (
        "positive validated news is offset by incomplete fundamentals coverage"
        if has_bull and has_high_bear
        else "validated evidence is insufficient for a directional upgrade"
    )
    key_level_count = len(key_levels) if isinstance(key_levels, list) else 0
    lines.append(f"- Recommendation: {recommendation} (HIGH)")
    lines.append(f"- Rationale: {rationale} for {ticker or 'the instrument'} (HIGH)")
    lines.append(
        f"- Strategic Action: wait for refreshed fundamentals and {key_level_count} validated market price levels before sizing new risk (HIGH)"
    )
    return "\n".join(lines).strip()


def build_trader_plan_fallback(
    state: dict[str, Any],
    reason: str = "",
    force_recommendation: str = "",
) -> str:
    investment_plan = str(state.get("investment_plan") or "")
    upper_plan = investment_plan.upper()
    if "SELL" in upper_plan:
        recommendation = "SELL"
    elif "BUY" in upper_plan:
        recommendation = "BUY"
    else:
        recommendation = "HOLD"

    market_structured = state.get("market_report_structured") or {}
    key_levels = market_structured.get("key_levels") or []
    price_level_count = len(key_levels) if isinstance(key_levels, list) else 0
    fundamentals_structured = state.get("fundamentals_report_structured") or {}
    fundamentals_status = str(fundamentals_structured.get("status") or "unknown")

    if force_recommendation:
        recommendation = force_recommendation.upper().strip()
    if price_level_count == 0 or fundamentals_status == "timeout_fallback":
        recommendation = "HOLD"

    lines = [
        f"- Research Manager's Verdict: {recommendation} derived from validated upstream evidence (HIGH)",
        f"- Entry Setup: no new entry because {price_level_count} validated market price levels are available in the structured packet (HIGH)",
        "- Risk Parameters: preserve existing risk controls and do not place a fresh order until fundamentals are complete (HIGH)",
        "- Catalyst Timeline: use only scanner ground-truth dates already present upstream; no new date inference was added here (MED)",
        f"- FINAL TRANSACTION PROPOSAL: **{recommendation}**",
    ]
    if reason:
        lines.insert(1, f"- Validation Guardrail: {reason} (HIGH)")
    return "\n".join(lines).strip()


def _extract_action_regex(text: str) -> ExtractionResult | None:
    """Return ExtractionResult via regex on known-format labels, or None on miss.

    Never returns a default — None means "no pattern matched".
    """
    raw = str(text or "")
    single_line_patterns = [
        # explicit proposal/recommendation labels (original six)
        r"FINAL\s+TRANSACTION\s+PROPOSAL\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"FINAL\s+RECOMMENDATION\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"RECOMMENDATION\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"BALANCED\s+ASSESSMENT\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"RATING\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"ACTION\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        # numbered-prefix variants: "1. Rating: Buy" / "1) Rating — Sell"
        r"^\s*\d+[.)]\s+(?:Final\s+)?Rating\s*[:\-—]\s*[*_]*(BUY|SELL|HOLD)\b",
    ]
    for pattern in single_line_patterns:
        m = re.search(pattern, raw, re.IGNORECASE | re.MULTILINE)
        if m:
            return ExtractionResult(
                action=m.group(1).upper(),
                confidence="high",
                source="regex",
                evidence_quote=None,
            )

    # Multi-line header patterns: bold/ATX header followed by action on next line
    # Covers: **1. Rating**\n**Buy**, **Rating**\n**Buy**, ### Rating\nBuy, etc.
    multi_line_pattern = re.compile(
        r"(?:#{1,3}\s*|[*_]{1,2})\d*[.)?\s]*(?:Final\s+)?Rating[*_]*\s*\n\s*[*_]*(BUY|SELL|HOLD)\b",
        re.IGNORECASE,
    )
    m = multi_line_pattern.search(raw)
    if m:
        return ExtractionResult(
            action=m.group(1).upper(),
            confidence="high",
            source="regex",
            evidence_quote=None,
        )

    return None


_EXTRACTION_SYSTEM_PROMPT = """\
You extract the final trading action from a portfolio manager's report.
The action must be one of BUY, SELL, or HOLD.
Return strict JSON — no prose, no markdown fences:
{"action": "BUY"|"SELL"|"HOLD", "confidence": "high"|"med"|"low", "evidence_quote": "<verbatim ≤200 chars>"}
Set confidence to "low" if the text is ambiguous or the action is not clearly stated.
The evidence_quote must be a direct verbatim excerpt from the text that shows the action."""


def _extract_action_llm(text: str, llm: Any) -> ExtractionResult:
    """Call LLM to extract action. Never raises — returns low-confidence sentinel on any failure.

    The sentinel has confidence="low" so the caller's hard-fail path triggers uniformly.
    """
    _sentinel = ExtractionResult(action="HOLD", confidence="low", source="llm", evidence_quote=None)
    try:
        messages = [
            SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=f"TEXT:\n<<<{text}>>>"),
        ]
        timeout = resolve_timeout("quick")
        response, invoke_error = invoke_with_timeout(llm, messages, timeout_seconds=timeout)
        if invoke_error is not None or response is None:
            return _sentinel
        raw = response.content if hasattr(response, "content") else str(response)
        try:
            parsed = extract_json(raw)
        except Exception:
            return _sentinel
        if not isinstance(parsed, dict):
            return _sentinel
        action = str(parsed.get("action") or "").upper()
        if action not in {"BUY", "SELL", "HOLD"}:
            return _sentinel
        confidence = str(parsed.get("confidence") or "").lower()
        if confidence not in {"high", "med", "low"}:
            return _sentinel
        evidence_quote = parsed.get("evidence_quote")
        if isinstance(evidence_quote, str):
            evidence_quote = evidence_quote[:200] or None
        else:
            evidence_quote = None
        return ExtractionResult(
            action=action,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
            source="llm",
            evidence_quote=evidence_quote,
        )
    except Exception:
        return _sentinel


def extract_action(text: str, llm: Any = None) -> ExtractionResult:
    """Two-stage action extractor. Raises ActionExtractionError on hard fail.

    Stage 1: regex (fast, deterministic, no LLM call).
    Stage 2: LLM fallback if regex misses (requires llm argument).

    Raises ActionExtractionError when:
    - regex misses AND llm is None (caller must provide llm for fallback)
    - regex misses AND LLM returns confidence=="low"
    - regex misses AND LLM errors (timeout, parse fail, etc.)
    """
    regex_result = _extract_action_regex(text)
    if regex_result is not None:
        return regex_result
    if llm is None:
        raise ActionExtractionError(text_excerpt=text[:300], last_attempt=None)
    llm_result = _extract_action_llm(text, llm=llm)
    if llm_result.confidence == "low":
        raise ActionExtractionError(text_excerpt=text[:300], last_attempt=llm_result)
    return llm_result


def _infer_recommendation(text: str, llm: Any = None) -> str:
    """Back-compat shim. Raises ActionExtractionError on hard fail (no HOLD default).
    
    Empty input returns HOLD without calling extraction (preserves existing tests).
    Non-empty input delegates to extract_action which raises ActionExtractionError
    if no pattern matches and either no LLM is provided or LLM returns low confidence.
    """
    if not str(text or "").strip():
        return "HOLD"
    return extract_action(text, llm=llm).action


def _infer_sentiment_direction(text: str) -> str:
    """Return dominant sentiment direction from prose."""
    upper = str(text or "").upper()
    bullish = upper.count("BULLISH") + upper.count("POSITIVE") + upper.count("OPTIMISTIC")
    bearish = upper.count("BEARISH") + upper.count("NEGATIVE") + upper.count("PESSIMISTIC")
    if bullish > bearish:
        return "bullish"
    if bearish > bullish:
        return "bearish"
    if bullish == bearish and bullish > 0:
        return "mixed"
    return "neutral"


def build_sentiment_report_structured(
    *,
    ticker: str,
    as_of_date: str,
    sentiment_report: str,
    contract_version: str = "sentiment_summary_v1",
    is_timeout_fallback: bool = False,
) -> dict[str, Any]:
    """Build a compact canonical contract for social-media/sentiment node output."""
    report = str(sentiment_report or "").strip()
    timeout_detected = is_timeout_fallback or "timed out after" in report.lower()
    if timeout_detected:
        status = "timeout_fallback"
        abort_reason = ""
    elif not report:
        status = "empty"
        abort_reason = ""
    else:
        status = "completed"
        abort_reason = ""

    bullet_count = len(re.findall(r"(?m)^\s*[-*]\s+", report))
    numeric_mentions = len(
        re.findall(r"\$[0-9]|[0-9]+(?:\.[0-9]+)?%|[0-9]+(?:\.[0-9]+)?\s*bps", report, re.IGNORECASE)
    )
    source_mentions = len(
        re.findall(
            r"\b(?:twitter|reddit|stocktwits|seeking alpha|social media|forum|youtube)\b",
            report,
            re.IGNORECASE,
        )
    )
    sentiment_direction = _infer_sentiment_direction(report)

    return {
        "ticker": str(ticker or "").strip().upper(),
        "as_of_date": str(as_of_date or "").strip(),
        "status": status,
        "contract_version": contract_version,
        "abort_reason": abort_reason,
        "claim_count": bullet_count,
        "sentiment_direction": sentiment_direction,
        "key_metrics": {
            "numeric_mentions": numeric_mentions,
            "source_mentions": source_mentions,
            "report_char_count": len(report),
        },
    }


def build_news_report_structured(
    *,
    ticker: str,
    as_of_date: str,
    payload: dict[str, Any],
    status: str,
    abort_reason: str = "",
    removed_claims: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a canonical news_report_v1 contract from a sanitized payload.

    This is the sole normalization point for news structured output. It validates
    the status, stamps contract metadata, computes key_metrics, and ensures the
    returned contract is always valid, even when given malformed inputs.

    Args:
        ticker: Company ticker symbol
        as_of_date: Report date in YYYY-MM-DD format
        payload: Sanitized news payload from validate/sanitize flow, or {} for failures
        status: One of: completed, empty, invalid_structured_payload,
                missing_structured_payload, aborted
        abort_reason: Error description for non-completed statuses
        removed_claims: Claims rejected during sanitization (for metrics)

    Returns:
        dict: Always a valid news_report_v1 contract, never raises
    """
    try:
        # Canonical news status set - no timeout_fallback or completed_sparse for news
        canonical_statuses = {
            "completed",
            "empty",
            "invalid_structured_payload",
            "missing_structured_payload",
            "aborted",
        }

        # Validate status
        status_str = str(status or "").strip()
        if status_str not in canonical_statuses:
            # Non-canonical status - return invalid contract
            return {
                "ticker": str(ticker or "").strip().upper(),
                "as_of_date": str(as_of_date or "").strip(),
                "status": "invalid_structured_payload",
                "contract_version": "news_report_v1",
                "abort_reason": f"Non-canonical status supplied: {status_str}",
                "report_title": f"{str(ticker or '').strip().upper()} News Analysis",
                "claims": [],
                "summary_table": [],
                "key_metrics": {
                    "claim_count": 0,
                    "summary_rows": 0,
                    "evidence_ids": 0,
                    "removed_claims": len(removed_claims or []),
                    "below_min_claims": False,
                },
            }

        # Validate payload is a dict
        if not isinstance(payload, dict):
            payload = {}

        # Extract and validate claims
        claims_raw = payload.get("claims") or []
        if not isinstance(claims_raw, list):
            claims_raw = []

        # Reconstruct claims with whitelisted fields and scan_date cleanup
        output_claims = []
        for claim in claims_raw:
            if not isinstance(claim, dict):
                # Malformed claim - treat as invalid_structured_payload
                return {
                    "ticker": str(ticker or "").strip().upper(),
                    "as_of_date": str(as_of_date or "").strip(),
                    "status": "invalid_structured_payload",
                    "contract_version": "news_report_v1",
                    "abort_reason": "Malformed claim entry in payload",
                    "report_title": f"{str(ticker or '').strip().upper()} News Analysis",
                    "claims": [],
                    "summary_table": [],
                    "key_metrics": {
                        "claim_count": 0,
                        "summary_rows": 0,
                        "evidence_ids": 0,
                        "removed_claims": len(removed_claims or []),
                        "below_min_claims": False,
                    },
                }

            source = str(claim.get("source") or "").strip()
            is_scanner = source == "Finviz Smart Money Scanner"

            # Build output claim with whitelisted fields
            output_claim = {
                "claim": str(claim.get("claim") or "").strip(),
                "source": source,
            }

            if is_scanner:
                # Scanner claims: retain scan_date, omit blank optional fields
                scan_date = str(claim.get("scan_date") or "").strip()
                if scan_date:
                    output_claim["scan_date"] = scan_date
                # Scanner claims may have blank published_at and evidence_id - omit if blank
                published_at = str(claim.get("published_at") or "").strip()
                if published_at:
                    output_claim["published_at"] = published_at
                evidence_id = str(claim.get("evidence_id") or "").strip()
                if evidence_id:
                    output_claim["evidence_id"] = evidence_id
            else:
                # Article claims: require non-empty evidence_id, include published_at, strip scan_date
                published_at = str(claim.get("published_at") or "").strip()
                evidence_id = str(claim.get("evidence_id") or "").strip()
                if not evidence_id:
                    # Non-scanner claim without evidence_id is invalid
                    return {
                        "ticker": str(ticker or "").strip().upper(),
                        "as_of_date": str(as_of_date or "").strip(),
                        "status": "invalid_structured_payload",
                        "contract_version": "news_report_v1",
                        "abort_reason": "Non-scanner claim missing required evidence_id",
                        "report_title": f"{str(ticker or '').strip().upper()} News Analysis",
                        "claims": [],
                        "summary_table": [],
                        "key_metrics": {
                            "claim_count": 0,
                            "summary_rows": 0,
                            "evidence_ids": 0,
                            "removed_claims": len(removed_claims or []),
                            "below_min_claims": False,
                        },
                    }
                output_claim["published_at"] = published_at
                output_claim["evidence_id"] = evidence_id
                # scan_date is stripped for non-scanner claims

            output_claims.append(output_claim)

        # Extract and validate summary table
        summary_raw = payload.get("summary_table") or []
        if not isinstance(summary_raw, list):
            summary_raw = []

        # Reconstruct summary rows with whitelisted fields
        output_summary = []
        for row in summary_raw:
            if not isinstance(row, dict):
                # Malformed row - treat as invalid_structured_payload
                return {
                    "ticker": str(ticker or "").strip().upper(),
                    "as_of_date": str(as_of_date or "").strip(),
                    "status": "invalid_structured_payload",
                    "contract_version": "news_report_v1",
                    "abort_reason": "Malformed summary_table entry in payload",
                    "report_title": f"{str(ticker or '').strip().upper()} News Analysis",
                    "claims": [],
                    "summary_table": [],
                    "key_metrics": {
                        "claim_count": 0,
                        "summary_rows": 0,
                        "evidence_ids": 0,
                        "removed_claims": len(removed_claims or []),
                        "below_min_claims": False,
                    },
                }

            source = str(row.get("source") or "").strip()
            is_scanner = source == "Finviz Smart Money Scanner"

            # Build output row with whitelisted fields
            output_row = {
                "date": str(row.get("date") or "").strip(),
                "event": str(row.get("event") or "").strip(),
                "metric": str(row.get("metric") or "").strip(),
                "value": str(row.get("value") or "").strip(),
                "source": source,
            }

            if is_scanner:
                # Scanner rows: retain scan_date
                scan_date = str(row.get("scan_date") or "").strip()
                if scan_date:
                    output_row["scan_date"] = scan_date
                # Scanner rows may have blank evidence_id - include if present
                evidence_id = str(row.get("evidence_id") or "").strip()
                if evidence_id:
                    output_row["evidence_id"] = evidence_id
            else:
                # Non-scanner rows: require evidence_id, strip scan_date
                evidence_id = str(row.get("evidence_id") or "").strip()
                if not evidence_id:
                    # Non-scanner row without evidence_id is invalid
                    return {
                        "ticker": str(ticker or "").strip().upper(),
                        "as_of_date": str(as_of_date or "").strip(),
                        "status": "invalid_structured_payload",
                        "contract_version": "news_report_v1",
                        "abort_reason": "Non-scanner summary_table row missing required evidence_id",
                        "report_title": f"{str(ticker or '').strip().upper()} News Analysis",
                        "claims": [],
                        "summary_table": [],
                        "key_metrics": {
                            "claim_count": 0,
                            "summary_rows": 0,
                            "evidence_ids": 0,
                            "removed_claims": len(removed_claims or []),
                            "below_min_claims": False,
                        },
                    }
                output_row["evidence_id"] = evidence_id

            output_summary.append(output_row)

        # Compute key_metrics
        claim_count = len(output_claims)
        summary_rows = len(output_summary)

        # Count unique evidence_ids across claims (non-empty)
        evidence_ids = set()
        for claim in output_claims:
            eid = claim.get("evidence_id")
            if eid:
                evidence_ids.add(eid)
        evidence_id_count = len(evidence_ids)

        removed_count = len(removed_claims or [])
        below_min_claims = bool(payload.get("below_min_claims"))

        # Synthesize report_title if missing
        report_title = payload.get("report_title")
        if not report_title:
            ticker_upper = str(ticker or "").strip().upper()
            report_title = f"{ticker_upper} News Analysis"

        # Build canonical contract
        return {
            "ticker": str(ticker or "").strip().upper(),
            "as_of_date": str(as_of_date or "").strip(),
            "status": status_str,
            "contract_version": "news_report_v1",
            "abort_reason": str(abort_reason or "").strip(),
            "report_title": str(report_title or "").strip(),
            "claims": output_claims,
            "summary_table": output_summary,
            "key_metrics": {
                "claim_count": claim_count,
                "summary_rows": summary_rows,
                "evidence_ids": evidence_id_count,
                "removed_claims": removed_count,
                "below_min_claims": below_min_claims,
            },
        }

    except Exception as e:
        # Defensive: if anything fails, return a valid invalid_structured_payload contract
        logger.exception("build_news_report_structured failed with exception")
        return {
            "ticker": str(ticker or "").strip().upper(),
            "as_of_date": str(as_of_date or "").strip(),
            "status": "invalid_structured_payload",
            "contract_version": "news_report_v1",
            "abort_reason": f"Normalizer exception: {str(e)}",
            "report_title": f"{str(ticker or '').strip().upper()} News Analysis",
            "claims": [],
            "summary_table": [],
            "key_metrics": {
                "claim_count": 0,
                "summary_rows": 0,
                "evidence_ids": 0,
                "removed_claims": len(removed_claims or []),
                "below_min_claims": False,
            },
        }


def build_investment_plan_structured(
    *,
    ticker: str,
    as_of_date: str,
    investment_plan: str,
    contract_version: str = "investment_plan_v1",
    is_timeout_fallback: bool = False,
    llm: Any = None,
) -> dict[str, Any]:
    """Build a compact canonical contract for research-manager output."""
    plan = str(investment_plan or "").strip()
    timeout_detected = is_timeout_fallback or "timed out" in plan.lower()
    recommendation: str | None
    if not plan:
        status = "empty"
        abort_reason = ""
        recommendation = "HOLD"
    elif timeout_detected:
        status = "timeout_fallback"
        abort_reason = ""
        recommendation = "HOLD"
    else:
        try:
            recommendation = _infer_recommendation(plan, llm=llm)
            status = "completed"
            abort_reason = ""
        except ActionExtractionError as exc:
            recommendation = None
            status = "extraction_failed"
            abort_reason = f"action_extraction_failed: {exc.text_excerpt}"
            logger.warning(
                "build_investment_plan_structured: action extraction failed for ticker=%s excerpt=%r",
                ticker,
                exc.text_excerpt,
            )
    bullet_count = len(re.findall(r"(?m)^\s*[-*]\s+", plan))
    numeric_mentions = len(
        re.findall(r"\$[0-9]|[0-9]+(?:\.[0-9]+)?%|[0-9]+(?:\.[0-9]+)?\s*bps", plan, re.IGNORECASE)
    )
    high_confidence = len(re.findall(r"\(HIGH\)", plan, re.IGNORECASE))
    med_confidence = len(re.findall(r"\(MED\)", plan, re.IGNORECASE))
    low_confidence = len(re.findall(r"\(LOW\)", plan, re.IGNORECASE))

    return {
        "ticker": str(ticker or "").strip().upper(),
        "as_of_date": str(as_of_date or "").strip(),
        "status": status,
        "contract_version": contract_version,
        "abort_reason": abort_reason,
        "recommendation": recommendation,
        "key_metrics": {
            "bullet_count": bullet_count,
            "numeric_mentions": numeric_mentions,
            "high_confidence_claims": high_confidence,
            "med_confidence_claims": med_confidence,
            "low_confidence_claims": low_confidence,
            "plan_char_count": len(plan),
        },
    }


def build_trader_plan_structured(
    *,
    ticker: str,
    as_of_date: str,
    trader_plan: str,
    contract_version: str = "trader_plan_v1",
    is_timeout_fallback: bool = False,
    llm: Any = None,
) -> dict[str, Any]:
    """Build a compact canonical contract for trader node output."""
    plan = str(trader_plan or "").strip()
    timeout_detected = is_timeout_fallback or "timed out" in plan.lower()
    final_action: str | None
    if not plan:
        status = "empty"
        abort_reason = ""
        final_action = "HOLD"
    elif timeout_detected:
        status = "timeout_fallback"
        abort_reason = ""
        final_action = "HOLD"
    else:
        try:
            final_action = _infer_recommendation(plan, llm=llm)
            status = "completed"
            abort_reason = ""
        except ActionExtractionError as exc:
            final_action = None
            status = "extraction_failed"
            abort_reason = f"action_extraction_failed: {exc.text_excerpt}"
            logger.warning(
                "build_trader_plan_structured: action extraction failed for ticker=%s excerpt=%r",
                ticker,
                exc.text_excerpt,
            )
    has_entry = bool(re.search(r"entry\s*(price|setup|point)", plan, re.IGNORECASE))
    has_stop = bool(re.search(r"stop[.\- ]?loss", plan, re.IGNORECASE))
    has_target = bool(re.search(r"take[.\- ]?profit|target\s*price", plan, re.IGNORECASE))
    has_catalyst = bool(
        re.search(r"catalyst|timeline|earnings|fomc|cpi|ex[.\- ]?div", plan, re.IGNORECASE)
    )
    numeric_mentions = len(
        re.findall(r"\$[0-9]|[0-9]+(?:\.[0-9]+)?%|[0-9]+(?:\.[0-9]+)?\s*bps", plan, re.IGNORECASE)
    )

    return {
        "ticker": str(ticker or "").strip().upper(),
        "as_of_date": str(as_of_date or "").strip(),
        "status": status,
        "contract_version": contract_version,
        "abort_reason": abort_reason,
        "final_action": final_action,
        "key_metrics": {
            "entry_setup_present": has_entry,
            "stop_loss_present": has_stop,
            "take_profit_present": has_target,
            "catalyst_dates_present": has_catalyst,
            "numeric_mentions": numeric_mentions,
            "plan_char_count": len(plan),
        },
    }


def build_risk_synthesis_structured(
    *,
    ticker: str,
    as_of_date: str,
    risk_synthesis: str,
    contract_version: str = "risk_synthesis_v1",
    is_timeout_fallback: bool = False,
    llm: Any = None,
) -> dict[str, Any]:
    """Build a compact canonical contract for risk synthesis node output."""
    text = str(risk_synthesis or "").strip()
    timeout_detected = is_timeout_fallback or "timed out" in text.lower()
    consensus_direction: str | None
    if not text:
        status = "empty"
        abort_reason = ""
        consensus_direction = "HOLD"
    elif timeout_detected:
        status = "timeout_fallback"
        abort_reason = ""
        consensus_direction = "HOLD"
    else:
        try:
            consensus_direction = _infer_recommendation(text, llm=llm)
            status = "completed"
            abort_reason = ""
        except ActionExtractionError as exc:
            consensus_direction = None
            status = "extraction_failed"
            abort_reason = f"action_extraction_failed: {exc.text_excerpt}"
            logger.warning(
                "build_risk_synthesis_structured: action extraction failed for ticker=%s excerpt=%r",
                ticker,
                exc.text_excerpt,
            )
    agreements = len(
        re.findall(
            r"(?i)\b(all\s+(?:three\s+)?analysts\s+agree|unanimous|shared\s+view|common\s+ground)",
            text,
        )
    )
    disagreements = len(
        re.findall(r"(?i)\b(disagree|dissent|contention|conflict\s+between|opposing\s+view)", text)
    )
    risk_mentions = len(
        re.findall(r"(?i)\b(risk|downside|drawdown|tail\s+risk|volatility)\b", text)
    )
    numeric_mentions = len(
        re.findall(r"\$[0-9]|[0-9]+(?:\.[0-9]+)?%|[0-9]+(?:\.[0-9]+)?\s*bps", text, re.IGNORECASE)
    )

    return {
        "ticker": str(ticker or "").strip().upper(),
        "as_of_date": str(as_of_date or "").strip(),
        "status": status,
        "contract_version": contract_version,
        "abort_reason": abort_reason,
        "consensus_direction": consensus_direction,
        "key_metrics": {
            "agreement_mentions": agreements,
            "disagreement_mentions": disagreements,
            "risk_mentions": risk_mentions,
            "numeric_mentions": numeric_mentions,
            "synthesis_char_count": len(text),
        },
    }


def build_final_decision_structured(
    *,
    ticker: str,
    as_of_date: str,
    final_decision: str,
    contract_version: str = "final_decision_v1",
    is_timeout_fallback: bool = False,
    llm: Any = None,
) -> dict[str, Any]:
    """Build a compact canonical contract for portfolio-manager final decision."""
    text = str(final_decision or "").strip()
    timeout_detected = is_timeout_fallback or "timed out" in text.lower()
    action: str | None
    if not text:
        status = "empty"
        abort_reason = ""
        action = "HOLD"
    elif timeout_detected:
        status = "timeout_fallback"
        abort_reason = ""
        action = "HOLD"
    else:
        try:
            action = _infer_recommendation(text, llm=llm)
            status = "completed"
            abort_reason = ""
        except ActionExtractionError as exc:
            action = None
            status = "extraction_failed"
            abort_reason = f"action_extraction_failed: {exc.text_excerpt}"
            logger.warning(
                "build_final_decision_structured: action extraction failed for ticker=%s excerpt=%r",
                ticker,
                exc.text_excerpt,
            )
    numeric_mentions = len(
        re.findall(r"\$[0-9]|[0-9]+(?:\.[0-9]+)?%|[0-9]+(?:\.[0-9]+)?\s*bps", text, re.IGNORECASE)
    )
    has_stop = bool(re.search(r"stop[.\- ]?loss", text, re.IGNORECASE))
    has_target = bool(re.search(r"take[.\- ]?profit|target\s*price", text, re.IGNORECASE))
    has_position_size = bool(
        re.search(r"position\s*(size|sizing|weight|allocation)", text, re.IGNORECASE)
    )
    excerpt = " ".join(text.split())[:200]

    return {
        "ticker": str(ticker or "").strip().upper(),
        "as_of_date": str(as_of_date or "").strip(),
        "status": status,
        "contract_version": contract_version,
        "abort_reason": abort_reason,
        "action": action,
        "key_metrics": {
            "numeric_mentions": numeric_mentions,
            "stop_loss_present": has_stop,
            "take_profit_present": has_target,
            "position_size_present": has_position_size,
            "decision_char_count": len(text),
        },
        "decision_excerpt": excerpt,
    }


def canonicalize_source_name(
    raw_source: str,
    allowed_source_names: Iterable[str] | None = None,
) -> str | None:
    """Return a canonical source id for an explicit citation string."""
    normalized = _normalize_source_name(raw_source)
    if not normalized:
        return None

    allowed_aliases = {
        _normalize_source_name(source)
        for source in (allowed_source_names or [])
        if _normalize_source_name(source)
    }
    if normalized in allowed_aliases:
        return normalized

    for canonical_id, metadata in CANONICAL_SOURCE_REGISTRY.items():
        aliases = {
            _normalize_source_name(metadata["display_name"]),
            *{_normalize_source_name(alias) for alias in metadata["aliases"]},
        }
        if normalized in aliases:
            return canonical_id
    return None


def extract_allowed_sources_from_context(context: str) -> set[str]:
    """Extract source names from prefetched context injected into the prompt.

    The news prefetched context is usually JSON-like and includes fields such as
    ``"source"`` and ``"source_domain"``. We intentionally keep the parser
    lightweight and permissive so validation can accept real source names shown
    to the model, even when they are not in the static registry.
    """
    if not context:
        return set()

    allowed: set[str] = set()

    json_field_patterns = [
        r'"source"\s*:\s*"([^"]+)"',
        r'"source_domain"\s*:\s*"([^"]+)"',
    ]
    for pattern in json_field_patterns:
        for match in re.finditer(pattern, context, re.IGNORECASE):
            source = _clean_source_candidate(match.group(1))
            if source:
                allowed.add(source)

    markdown_patterns = [
        r"\bSource:\s*([^\n|]+)",
        r"\(source:\s*([^)]+)\)",
    ]
    for pattern in markdown_patterns:
        for match in re.finditer(pattern, context, re.IGNORECASE):
            source = _clean_source_candidate(match.group(1))
            if source:
                allowed.add(source)

    return allowed


def parse_structured_news_payload(output: str) -> dict[str, Any]:
    """Parse the news analyst's JSON payload and normalize top-level fields."""
    payload = extract_json(output)
    claims = payload.get("claims")
    summary_table = payload.get("summary_table")

    payload["claims"] = claims if isinstance(claims, list) else []
    payload["summary_table"] = summary_table if isinstance(summary_table, list) else []
    payload["ticker"] = str(payload.get("ticker") or "").strip().upper()
    payload["report_title"] = str(payload.get("report_title") or "").strip()
    return payload


def validate_structured_news_payload(
    output: str,
    ticker: str,
    *,
    min_claims: int = 3,
) -> StructuredNewsValidationResult:
    """Validate the analyst's structured JSON before provenance checks."""
    try:
        payload = parse_structured_news_payload(output)
    except ValueError as exc:
        return StructuredNewsValidationResult(
            False,
            str(exc),
            code="invalid_json",
        )

    ticker_upper = str(ticker or "").strip().upper()
    if not ticker_upper:
        return StructuredNewsValidationResult(
            False,
            "Empty ticker",
            payload=payload,
            code="empty_ticker",
        )

    if payload.get("ticker") != ticker_upper:
        return StructuredNewsValidationResult(
            False,
            f"Structured payload ticker '{payload.get('ticker')}' does not match expected ticker '{ticker_upper}'.",
            payload=payload,
            code="ticker_mismatch",
        )

    claims = payload["claims"]
    if len(claims) < min_claims:
        return StructuredNewsValidationResult(
            False,
            f"Structured payload has only {len(claims)} claims (expected {min_claims}+).",
            payload=payload,
            code="insufficient_claims",
        )

    valid_claims = 0
    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            return StructuredNewsValidationResult(
                False,
                f"Claim {index} is not a JSON object.",
                payload=payload,
                code="invalid_claim_shape",
            )

        summary = str(claim.get("claim") or "").strip()
        source = str(claim.get("source") or "").strip()
        published_at = str(claim.get("published_at") or "").strip()
        evidence_id = str(claim.get("evidence_id") or "").strip()

        if not summary:
            return StructuredNewsValidationResult(
                False,
                f"Claim {index} is missing 'claim' text.",
                payload=payload,
                code="missing_claim_text",
            )
        if not source:
            return StructuredNewsValidationResult(
                False,
                f"Claim {index} is missing 'source'.",
                payload=payload,
                code="missing_source",
            )
        if source == "Finviz Smart Money Scanner":
            scan_date = str(claim.get("scan_date") or "").strip()
            if not scan_date:
                return StructuredNewsValidationResult(
                    False,
                    f"Scanner claim {index} is missing 'scan_date'.",
                    payload=payload,
                    code="missing_scan_date",
                )
        else:
            if not published_at:
                return StructuredNewsValidationResult(
                    False,
                    f"Claim {index} is missing 'published_at'.",
                    payload=payload,
                    code="missing_published_at",
                )
            if not evidence_id:
                return StructuredNewsValidationResult(
                    False,
                    f"Claim {index} is missing 'evidence_id'.",
                    payload=payload,
                    code="missing_evidence_id",
                )

        # Accept claim as ticker-relevant if the claim text mentions the ticker symbol
        # OR if the claim is anchored to a specific evidence record (the news feed was
        # already pre-filtered for this ticker, so an evidence_id guarantees relevance
        # even when the model uses the company's full name rather than its symbol).
        if ticker_upper in summary.upper() or bool(evidence_id):
            valid_claims += 1

    if valid_claims == 0:
        return StructuredNewsValidationResult(
            False,
            f"No structured claims explicitly mention {ticker_upper}.",
            payload=payload,
            code="ticker_relevance",
        )

    return StructuredNewsValidationResult(
        True,
        "Valid structured news payload",
        payload=payload,
    )


def sanitize_structured_news_payload(
    payload: dict[str, Any],
    *,
    ticker: str,
    allowed_source_names: Iterable[str] | None = None,
    allowed_evidence_ids: Iterable[str] | None = None,
    evidence_records_by_id: dict[str, Any] | None = None,
    min_claims: int = 2,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop unsupported claims and summary rows using run-scoped evidence."""
    claims = payload.get("claims")
    rows = payload.get("summary_table")
    if not isinstance(claims, list):
        claims = []
    if not isinstance(rows, list):
        rows = []

    allowed_sources = {
        str(item).strip() for item in (allowed_source_names or []) if str(item).strip()
    }
    allowed_ids = {str(item).strip() for item in (allowed_evidence_ids or []) if str(item).strip()}
    records_by_id = evidence_records_by_id or {}

    kept_claims: list[dict[str, Any]] = []
    removed_claims: list[dict[str, Any]] = []
    kept_ids: set[str] = set()

    for claim in claims:
        if not isinstance(claim, dict):
            removed_claims.append({"reason": "invalid_claim_shape", "claim": claim})
            continue

        normalized = dict(claim)
        source = str(normalized.get("source") or "").strip()
        evidence_id = str(normalized.get("evidence_id") or "").strip()
        published_at = str(normalized.get("published_at") or "").strip()

        if source == "Finviz Smart Money Scanner":
            scan_date = str(normalized.get("scan_date") or "").strip()
            if not scan_date:
                removed_claims.append({"reason": "missing_scan_date", "claim": claim})
                continue
            kept_claims.append(normalized)
            continue

        record = records_by_id.get(evidence_id)
        if not evidence_id or evidence_id not in allowed_ids or record is None:
            removed_claims.append({"reason": "unknown_evidence_id", "claim": claim})
            continue

        if source not in allowed_sources or source != getattr(record, "source", source):
            removed_claims.append({"reason": "source_mismatch", "claim": claim})
            continue

        if published_at and published_at != getattr(record, "published_at", published_at):
            removed_claims.append({"reason": "published_at_mismatch", "claim": claim})
            continue

        normalized["published_at"] = getattr(record, "published_at", published_at)
        normalized["source"] = getattr(record, "source", source)
        normalized["evidence_id"] = evidence_id
        kept_claims.append(normalized)
        kept_ids.add(evidence_id)

    kept_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        normalized = dict(row)
        source = str(normalized.get("source") or "").strip()
        evidence_id = str(normalized.get("evidence_id") or "").strip()
        if source == "Finviz Smart Money Scanner":
            scan_date = str(normalized.get("scan_date") or "").strip()
            if scan_date:
                kept_rows.append(normalized)
            continue

        if evidence_id not in kept_ids:
            continue
        record = records_by_id.get(evidence_id)
        if record is None:
            continue
        normalized["source"] = getattr(record, "source", source)
        normalized["date"] = str(
            normalized.get("date") or getattr(record, "published_at", "")
        ).strip()
        kept_rows.append(normalized)

    sanitized = {
        "ticker": str(payload.get("ticker") or ticker).strip().upper(),
        "report_title": str(payload.get("report_title") or "").strip(),
        "claims": kept_claims,
        "summary_table": kept_rows,
    }
    if len(kept_claims) < min_claims:
        sanitized["below_min_claims"] = True
        logger.warning(
            "sanitize_structured_news_payload: only %d claims kept (min_claims=%d) for %s",
            len(kept_claims),
            min_claims,
            ticker,
        )
    return sanitized, removed_claims


def render_structured_news_payload(payload: dict[str, Any], ticker: str) -> str:
    """Render validated structured news back into markdown for downstream nodes."""
    ticker_upper = str(ticker or payload.get("ticker") or "").strip().upper()
    lines = [payload.get("report_title") or f"{ticker_upper} News Analysis", ""]

    claims = payload.get("claims") or []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        summary = str(claim.get("claim") or "").strip()
        if not summary:
            continue
        if ticker_upper not in summary.upper():
            summary = f"{ticker_upper}: {summary}"

        source = str(claim.get("source") or "").strip()
        evidence_id = str(claim.get("evidence_id") or "").strip()
        if source == "Finviz Smart Money Scanner":
            scan_date = str(claim.get("scan_date") or "").strip()
            lines.append(
                f"- {summary} [Source: Finviz Smart Money Scanner | Scan Date: {scan_date}]"
            )
            continue

        published_at = str(claim.get("published_at") or "").strip()
        citation = f"[Source: {source} | Published: {published_at}]"
        if evidence_id:
            citation += f" [Evidence ID: {evidence_id}]"
        lines.append(f"- {summary} {citation}")

    rows = payload.get("summary_table") or []
    if rows:
        lines.extend(
            [
                "",
                "### Summary Table",
                "",
                "| Date | Event | Metric | Value | Source | Evidence ID |",
                "|------|-------|--------|-------|--------|-------------|",
            ]
        )
        for row in rows:
            if not isinstance(row, dict):
                continue
            date = str(row.get("date") or row.get("published_at") or "").strip()
            event = str(row.get("event") or row.get("claim") or "").strip()
            metric = str(row.get("metric") or "").strip()
            value = str(row.get("value") or "").strip()
            source = str(row.get("source") or "").strip()
            evidence_id = str(row.get("evidence_id") or "").strip()
            lines.append(f"| {date} | {event} | {metric} | {value} | {source} | {evidence_id} |")

    return "\n".join(line for line in lines if line is not None).strip()


def validate_news_analysis_detailed(
    output: str,
    ticker: str,
    allowed_source_names: Iterable[str] | None = None,
    allowed_evidence_ids: Iterable[str] | None = None,
    enforce_provenance: bool = True,
    min_ticker_mentions: int = 5,
) -> ValidationResult:
    """Detailed validation result used by fail-closed retry logic."""
    if not output or not ticker:
        return ValidationResult(False, "Empty output or ticker", "empty_input")

    # First check basic ticker relevance
    is_valid, reason = validate_ticker_relevance(
        output,
        ticker,
        min_mentions=min_ticker_mentions,
        check_article_refs=True,
    )

    if not is_valid:
        return ValidationResult(False, reason, "ticker_relevance")

    # Check for anti-patterns (generic portfolio advice instead of news analysis)
    generic_patterns = [
        r"portfolio\s+diversification",
        r"asset\s+allocation",
        r"risk\s+tolerance",
        r"investment\s+horizon",
        r"dollar-cost averaging",
        r"rebalancing\s+strategy",
    ]

    generic_matches = sum(
        1 for pattern in generic_patterns if re.search(pattern, output, re.IGNORECASE)
    )

    if generic_matches >= 3:
        return ValidationResult(
            False,
            f"Output contains {generic_matches} generic portfolio strategy terms. "
            "This suggests hallucinated content rather than news analysis. "
            "News analysis should focus on specific events, not generic investment advice.",
            "generic_portfolio_advice",
        )

    has_numbers = bool(re.search(r"\$\d+|\d+%|\d+\.\d+%", output))
    has_dates = bool(re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}", output))

    if not has_numbers and not has_dates:
        return ValidationResult(
            False,
            "Output lacks specific numbers or dates. "
            "News analysis should cite specific figures and dates from articles.",
            "missing_quant_details",
        )

    if enforce_provenance:
        explicit_sources = extract_explicit_sources(
            output,
            allowed_source_names=allowed_source_names,
        )
        unknown_sources = sorted(
            {
                source
                for source in explicit_sources
                if canonicalize_source_name(source, allowed_source_names=allowed_source_names)
                is None
            }
        )
        if unknown_sources:
            return ValidationResult(
                False,
                "Unknown source citations detected: "
                + ", ".join(unknown_sources)
                + ". Use only canonical source names present in the provided context.",
                "unknown_source",
            )

        explicit_evidence_ids = extract_evidence_ids(output)
        allowed_ids = {
            str(item).strip() for item in (allowed_evidence_ids or []) if str(item).strip()
        }
        unknown_evidence_ids = sorted(
            {evidence_id for evidence_id in explicit_evidence_ids if evidence_id not in allowed_ids}
        )
        if unknown_evidence_ids:
            return ValidationResult(
                False,
                "Unknown evidence IDs detected: "
                + ", ".join(unknown_evidence_ids)
                + ". Use only evidence IDs persisted for the current run.",
                "unknown_evidence_id",
            )

    if _mentions_scanner_context(output) and not SCANNER_CITATION_PATTERN.search(output):
        return ValidationResult(
            False,
            "Scanner-derived claims require the exact citation format "
            "[Source: Finviz Smart Money Scanner | Scan Date: YYYY-MM-DD].",
            "missing_scanner_citation",
        )

    if _has_scanner_sec_conflation(output):
        return ValidationResult(
            False,
            "Finviz scanner data is being presented as SEC/Form 4 evidence. "
            "Scanner-derived claims must remain attributed to Finviz Smart Money Scanner.",
            "scanner_sec_conflation",
        )

    return ValidationResult(True, "Valid news analysis with specific data points")


def _normalize_source_name(raw_source: str) -> str:
    source = re.sub(r"\s+", " ", str(raw_source or "").strip().lower())
    source = source.strip(" .,:;()[]{}\"'")
    if source.startswith("the "):
        source = source[4:].strip()
    return source


def extract_explicit_sources(
    output: str,
    allowed_source_names: Iterable[str] | None = None,
) -> list[str]:
    """Extract only explicit attribution spans to minimize false positives."""
    matches: list[str] = []

    explicit_patterns = [
        r"\[Source:\s*([^\]|]+)",
        r"\bSource:\s*([^\n\]|]+)",
        r"\bAccording to\s+([A-Z][A-Za-z0-9&.' /-]{1,80}?)(?=\s+(?:on|dated|,|\())",
        r"\b([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,4})\s+"
        r"(?:reported|said|noted|wrote|published|revealed)\b",
    ]

    for pattern in explicit_patterns:
        for match in re.finditer(pattern, output):
            candidate = _clean_source_candidate(match.group(1))
            if candidate and _is_explicit_source_candidate(
                candidate,
                allowed_source_names=allowed_source_names,
            ):
                matches.append(candidate)

    return matches


def extract_evidence_ids(output: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in EVIDENCE_ID_PATTERN.finditer(output or "")
        if match.group(1).strip()
    ]


def filter_news_report_by_provenance(
    output: str,
    *,
    allowed_source_names: Iterable[str] | None = None,
    allowed_evidence_ids: Iterable[str] | None = None,
) -> tuple[str, list[str]]:
    """Remove bullet lines that cite unknown sources or evidence IDs."""
    allowed_ids = {str(item).strip() for item in (allowed_evidence_ids or []) if str(item).strip()}
    kept_lines: list[str] = []
    removed_lines: list[str] = []

    for line in (output or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            kept_lines.append(line)
            continue

        evidence_ids = extract_evidence_ids(line)
        if evidence_ids and any(evidence_id not in allowed_ids for evidence_id in evidence_ids):
            removed_lines.append(line)
            continue

        explicit_sources = extract_explicit_sources(
            line,
            allowed_source_names=allowed_source_names,
        )
        if explicit_sources and any(
            canonicalize_source_name(source, allowed_source_names=allowed_source_names) is None
            for source in explicit_sources
        ):
            removed_lines.append(line)
            continue

        kept_lines.append(line)

    sanitized = "\n".join(kept_lines)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    return sanitized, removed_lines


def _clean_source_candidate(candidate: str) -> str:
    candidate = re.split(r"\s+\|\s+", str(candidate or "").strip())[0]
    candidate = re.split(r"\s+(?:on|dated)\s+\d{4}-\d{2}-\d{2}", candidate, maxsplit=1)[0]
    candidate = candidate.strip(" .,:;()[]{}\"'")
    if not candidate or len(candidate) < 2:
        return ""
    return candidate


def _is_explicit_source_candidate(
    candidate: str,
    *,
    allowed_source_names: Iterable[str] | None = None,
) -> bool:
    normalized = _normalize_source_name(candidate)
    if not normalized or normalized in _GENERIC_SOURCE_CANDIDATES:
        return False

    if canonicalize_source_name(candidate, allowed_source_names=allowed_source_names) is not None:
        return True

    # Short all-caps tokens are usually ticker symbols in prose
    # (e.g. "USO reported...", "JPM said..."), not publication names.
    compact_candidate = re.sub(r"[^A-Za-z]", "", candidate)
    if compact_candidate.isupper() and 1 <= len(compact_candidate) <= 5:
        return False

    tokens = normalized.split()
    generic_tokens = {
        "company",
        "management",
        "report",
        "reports",
        "article",
        "articles",
        "market",
        "data",
        "analyst",
        "analysts",
        "investor",
        "investors",
    }
    if len(tokens) <= 2 and all(token in generic_tokens for token in tokens):
        return False

    return True


def _mentions_scanner_context(output: str) -> bool:
    output_lower = output.lower()
    return any(keyword in output_lower for keyword in SCANNER_KEYWORDS)


def _has_scanner_sec_conflation(output: str) -> bool:
    output_lower = output.lower()
    if not SCANNER_CITATION_PATTERN.search(output):
        return False
    if (
        "sec form 4" not in output_lower
        and "form 4" not in output_lower
        and "sec filing" not in output_lower
    ):
        return False

    for block in _iter_output_blocks(output):
        block_lower = block.lower()
        if SCANNER_CITATION_PATTERN.search(block) and (
            "sec form 4" in block_lower or "form 4" in block_lower or "sec filing" in block_lower
        ):
            return True
    return False


def _iter_output_blocks(output: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []

    for line in (output or "").splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue

        if stripped.startswith(("-", "*")) and current:
            blocks.append("\n".join(current))
            current = [line]
            continue

        current.append(line)

    if current:
        blocks.append("\n".join(current))
    return blocks


def validate_ticker_relevance(
    output: str, ticker: str, min_mentions: int = 3, check_article_refs: bool = True
) -> tuple[bool, str]:
    """
    Validate that agent output actually references the ticker.

    This catches hallucinations where the LLM produces generic content
    instead of analyzing the ticker-specific data provided.

    Args:
        output: Agent's generated report
        ticker: Expected ticker symbol
        min_mentions: Minimum times ticker should appear
        check_article_refs: Check for explicit article/source references

    Returns:
        (is_valid, reason) tuple
            - is_valid: True if output passes validation
            - reason: Human-readable explanation of validation result

    Examples:
        >>> validate_ticker_relevance("Generic risk advice...", "RIG", min_mentions=3)
        (False, "Ticker 'RIG' mentioned only 0 times (expected 3+). ...")

        >>> validate_ticker_relevance("RIG downgrade by Clarksons on 2026-03-15...", "RIG")
        (True, "Valid ticker-relevant output")
    """
    if not output or not ticker:
        return (False, "Empty output or ticker")

    ticker_upper = ticker.upper()

    # Count ticker mentions (case-insensitive, word boundaries)
    mentions = len(re.findall(rf"\b{re.escape(ticker_upper)}\b", output, re.IGNORECASE))

    if mentions < min_mentions:
        return (
            False,
            f"Ticker '{ticker}' mentioned only {mentions} times (expected {min_mentions}+). "
            "Output may be hallucinated generic content rather than ticker-specific analysis.",
        )

    # Check for actual source citations (indicates grounding in provided news data).
    # Patterns require explicit attribution syntax — not just words that happen to appear
    # in generic prose (e.g. "analysts expect..." is NOT a citation).
    if check_article_refs:
        article_indicators = [
            # Explicit attribution: "According to Reuters", "per Bloomberg", etc.
            r"\baccording\s+to\s+\w+",
            # Named source with a reporting verb: "Reuters reported", "Bloomberg said"
            r"\b\w+\s+(?:reported|said|noted|wrote|published|revealed)",
            # Inline source attribution: "(Source: ...)"
            r"\bsource\s*:",
            # Date + source combo: signals a real citation with temporal grounding
            r"\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
            r"\d{1,2}/\d{1,2}/\d{4}",  # MM/DD/YYYY
            # Quoted headline patterns: text in quotes following a verb or "titled"
            r'["\']\s*[A-Z][^"\']{10,}["\']',
            # News publication names that imply a real source
            r"\b(?:Reuters|Bloomberg|CNBC|WSJ|Wall Street Journal|Financial Times|"
            r"MarketWatch|Seeking Alpha|Barron\'s|Forbes|StocksToTrade|"
            r"Zacks|TheStreet|Motley Fool)\b",
        ]

        has_article_ref = any(
            re.search(pattern, output, re.IGNORECASE) for pattern in article_indicators
        )

        if not has_article_ref:
            return (
                False,
                "No article citations, named sources, publication names, or dated references found. "
                "Output may not be grounded in the provided news data.",
            )

    return (True, "Valid ticker-relevant output")


def validate_news_analysis(output: str, ticker: str) -> tuple[bool, str]:
    """
    Specialized validation for news analyst output.

    Checks for:
    - Ticker mentions
    - Source citations
    - Dates
    - Specific facts/numbers
    - NOT generic portfolio advice

    Args:
        output: News analyst's generated report
        ticker: Expected ticker symbol

    Returns:
        (is_valid, reason) tuple
    """
    result = validate_news_analysis_detailed(output, ticker)
    return (result.is_valid, result.reason)


def format_validation_warning(output: str, ticker: str, reason: str) -> str:
    """
    Format a validation warning to prepend to output.

    Args:
        output: Original agent output
        ticker: Ticker symbol
        reason: Validation failure reason

    Returns:
        Output with prepended warning banner
    """
    warning_banner = f"""
⚠️ **OUTPUT VALIDATION WARNING** ⚠️

Ticker: {ticker}
Issue: {reason}

This output may not meet quality standards. It should be reviewed before use.
The agent may have hallucinated generic content instead of analyzing the provided data.

---

""".strip()

    return f"{warning_banner}\n\n{output}"


def log_validation_result(
    agent_name: str, ticker: str, is_valid: bool, reason: str, output_preview: str = ""
):
    """
    Log validation results for monitoring and debugging.

    Args:
        agent_name: Name of the agent being validated
        ticker: Ticker symbol
        is_valid: Whether validation passed
        reason: Validation result reason
        output_preview: First 200 chars of output for debugging
    """
    log_level = logging.INFO if is_valid else logging.WARNING

    preview = output_preview[:200] + "..." if len(output_preview) > 200 else output_preview

    logger.log(
        log_level,
        f"{agent_name} validation for {ticker}: {'PASS' if is_valid else 'FAIL'} - {reason}",
    )

    if not is_valid and output_preview:
        logger.debug(f"Output preview: {preview}")
