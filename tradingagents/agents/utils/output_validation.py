"""Output validation utilities for detecting hallucinated or off-topic responses.

This module provides validation functions to check if agent outputs are actually
analyzing the provided data rather than hallucinating generic content.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    reason: str
    code: str = "ok"


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
SCANNER_KEYWORDS = (
    "smart money",
    "unusual volume",
    "institutional flow",
    "flow signal",
    "scanner context",
    "insider buying",
)


def canonicalize_source_name(raw_source: str) -> Optional[str]:
    """Return a canonical source id for an explicit citation string."""
    normalized = _normalize_source_name(raw_source)
    if not normalized:
        return None

    for canonical_id, metadata in CANONICAL_SOURCE_REGISTRY.items():
        aliases = {_normalize_source_name(metadata["display_name"]), *{
            _normalize_source_name(alias) for alias in metadata["aliases"]
        }}
        if normalized in aliases:
            return canonical_id
    return None


def validate_news_analysis_detailed(output: str, ticker: str) -> ValidationResult:
    """Detailed validation result used by fail-closed retry logic."""
    if not output or not ticker:
        return ValidationResult(False, "Empty output or ticker", "empty_input")

    # First check basic ticker relevance
    is_valid, reason = validate_ticker_relevance(
        output, ticker, min_mentions=5, check_article_refs=True
    )

    if not is_valid:
        return ValidationResult(False, reason, "ticker_relevance")

    # Check for anti-patterns (generic portfolio advice instead of news analysis)
    generic_patterns = [
        r'portfolio\s+diversification',
        r'asset\s+allocation',
        r'risk\s+tolerance',
        r'investment\s+horizon',
        r'dollar-cost averaging',
        r'rebalancing\s+strategy',
    ]

    generic_matches = sum(
        1 for pattern in generic_patterns
        if re.search(pattern, output, re.IGNORECASE)
    )

    if generic_matches >= 3:
        return ValidationResult(
            False,
            f"Output contains {generic_matches} generic portfolio strategy terms. "
            "This suggests hallucinated content rather than news analysis. "
            "News analysis should focus on specific events, not generic investment advice.",
            "generic_portfolio_advice",
        )

    has_numbers = bool(re.search(r'\$\d+|\d+%|\d+\.\d+%', output))
    has_dates = bool(re.search(r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}', output))

    if not has_numbers and not has_dates:
        return ValidationResult(
            False,
            "Output lacks specific numbers or dates. "
            "News analysis should cite specific figures and dates from articles.",
            "missing_quant_details",
        )

    explicit_sources = _extract_explicit_sources(output)
    unknown_sources = sorted(
        {
            source for source in explicit_sources
            if canonicalize_source_name(source) is None
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
    return source


def _extract_explicit_sources(output: str) -> list[str]:
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
            if candidate:
                matches.append(candidate)

    return matches


def _clean_source_candidate(candidate: str) -> str:
    candidate = re.split(r"\s+\|\s+", str(candidate or "").strip())[0]
    candidate = re.split(r"\s+(?:on|dated)\s+\d{4}-\d{2}-\d{2}", candidate, maxsplit=1)[0]
    candidate = candidate.strip(" .,:;()[]{}\"'")
    if not candidate or len(candidate) < 2:
        return ""
    return candidate


def _mentions_scanner_context(output: str) -> bool:
    output_lower = output.lower()
    return any(keyword in output_lower for keyword in SCANNER_KEYWORDS)


def _has_scanner_sec_conflation(output: str) -> bool:
    output_lower = output.lower()
    if not SCANNER_CITATION_PATTERN.search(output):
        return False
    if "sec form 4" not in output_lower and "form 4" not in output_lower and "sec filing" not in output_lower:
        return False

    scanner_windows = re.finditer(
        r"(.{0,160}\[Source:\s*Finviz Smart Money Scanner\s*\|\s*Scan Date:\s*\d{4}-\d{2}-\d{2}\].{0,160})",
        output,
        re.IGNORECASE | re.DOTALL,
    )
    for window in scanner_windows:
        chunk = window.group(1).lower()
        if "sec form 4" in chunk or "form 4" in chunk or "sec filing" in chunk:
            return True
    return False


def validate_ticker_relevance(
    output: str,
    ticker: str,
    min_mentions: int = 3,
    check_article_refs: bool = True
) -> Tuple[bool, str]:
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
    mentions = len(re.findall(rf'\b{re.escape(ticker_upper)}\b', output, re.IGNORECASE))
    
    if mentions < min_mentions:
        return (
            False,
            f"Ticker '{ticker}' mentioned only {mentions} times (expected {min_mentions}+). "
            "Output may be hallucinated generic content rather than ticker-specific analysis."
        )
    
    # Check for actual source citations (indicates grounding in provided news data).
    # Patterns require explicit attribution syntax — not just words that happen to appear
    # in generic prose (e.g. "analysts expect..." is NOT a citation).
    if check_article_refs:
        article_indicators = [
            # Explicit attribution: "According to Reuters", "per Bloomberg", etc.
            r'\baccording\s+to\s+\w+',
            # Named source with a reporting verb: "Reuters reported", "Bloomberg said"
            r'\b\w+\s+(?:reported|said|noted|wrote|published|revealed)',
            # Inline source attribution: "(Source: ...)"
            r'\bsource\s*:',
            # Date + source combo: signals a real citation with temporal grounding
            r'\d{4}-\d{2}-\d{2}',   # YYYY-MM-DD
            r'\d{1,2}/\d{1,2}/\d{4}',  # MM/DD/YYYY
            # Quoted headline patterns: text in quotes following a verb or "titled"
            r'["\']\s*[A-Z][^"\']{10,}["\']',
            # News publication names that imply a real source
            r'\b(?:Reuters|Bloomberg|CNBC|WSJ|Wall Street Journal|Financial Times|'
            r'MarketWatch|Seeking Alpha|Barron\'s|Forbes|StocksToTrade|'
            r'Zacks|TheStreet|Motley Fool)\b',
        ]

        has_article_ref = any(
            re.search(pattern, output, re.IGNORECASE)
            for pattern in article_indicators
        )

        if not has_article_ref:
            return (
                False,
                "No article citations, named sources, publication names, or dated references found. "
                "Output may not be grounded in the provided news data."
            )
    
    return (True, "Valid ticker-relevant output")


def validate_news_analysis(output: str, ticker: str) -> Tuple[bool, str]:
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
    agent_name: str,
    ticker: str,
    is_valid: bool,
    reason: str,
    output_preview: str = ""
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
        f"{agent_name} validation for {ticker}: "
        f"{'PASS' if is_valid else 'FAIL'} - {reason}"
    )
    
    if not is_valid and output_preview:
        logger.debug(f"Output preview: {preview}")
