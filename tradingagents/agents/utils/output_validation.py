"""Output validation utilities for detecting hallucinated or off-topic responses.

This module provides validation functions to check if agent outputs are actually
analyzing the provided data rather than hallucinating generic content.
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


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
    ticker_lower = ticker.lower()
    
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
    # First check basic ticker relevance
    is_valid, reason = validate_ticker_relevance(
        output, ticker, min_mentions=5, check_article_refs=True
    )
    
    if not is_valid:
        return (is_valid, reason)
    
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
    
    # If output has multiple generic portfolio strategy terms, it's likely hallucinated
    if generic_matches >= 3:
        return (
            False,
            f"Output contains {generic_matches} generic portfolio strategy terms. "
            "This suggests hallucinated content rather than news analysis. "
            "News analysis should focus on specific events, not generic investment advice."
        )
    
    # Check for specific quantitative data (good sign)
    has_numbers = bool(re.search(r'\$\d+|\d+%|\d+\.\d+%', output))
    has_dates = bool(re.search(r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}', output))
    
    if not has_numbers and not has_dates:
        return (
            False,
            "Output lacks specific numbers or dates. "
            "News analysis should cite specific figures and dates from articles."
        )
    
    return (True, "Valid news analysis with specific data points")


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
