"""Context filtering utilities for reducing token count while preserving ticker-relevant data.

This module provides functions to filter scanner context packets to only include
ticker-relevant information, reducing context from ~10K to ~3-4K tokens.
"""

import logging
import re

logger = logging.getLogger(__name__)


# Sector relationship mapping for finding related sectors
RELATED_SECTORS = {
    "Energy": ["Materials", "Industrials"],
    "Materials": ["Energy", "Industrials"],
    "Industrials": ["Materials", "Technology"],
    "Technology": ["Communication Services", "Consumer Discretionary"],
    "Communication Services": ["Technology", "Consumer Discretionary"],
    "Consumer Discretionary": ["Consumer Staples", "Communication Services"],
    "Consumer Staples": ["Consumer Discretionary", "Health Care"],
    "Health Care": ["Consumer Staples", "Technology"],
    "Financials": ["Real Estate", "Industrials"],
    "Real Estate": ["Financials", "Consumer Discretionary"],
    "Utilities": ["Energy", "Real Estate"],
}


def filter_scanner_context_for_ticker(scanner_context: str, ticker: str) -> str:
    """
    Reduce scanner context packet to only ticker-relevant data.
    
    Target: Reduce from ~10K to ~3-4K tokens
    
    Args:
        scanner_context: Full scanner context packet string
        ticker: Ticker symbol to filter for (e.g., "RIG")
    
    Returns:
        Filtered scanner context packet with only ticker-relevant data
    """
    if not scanner_context or not ticker:
        return scanner_context
    
    try:
        ticker = ticker.upper()
        
        # Split into sections using the ## headers
        sections = _split_scanner_sections(scanner_context)
        
        # Section I: Ticker-specific thesis - KEEP AS-IS (use partial key match)
        section_i = _find_section_by_prefix(sections, "I. TICKER")
        
        # Section II: Structured live data - FILTER
        section_ii_raw = _find_section_by_prefix(sections, "II. STRUCTURED")
        section_ii = _filter_structured_data(section_ii_raw, ticker)
        
        # Section III: Smart money - FILTER to ticker-specific
        section_iii_raw = _find_section_by_prefix(sections, "III. SMART")
        section_iii = filter_smart_money_for_ticker(section_iii_raw, ticker)
        
        # Section IV: Factor alignment & drift - FILTER to ticker-specific
        section_iv_raw = _find_section_by_prefix(sections, "IV. FACTOR")
        section_iv = filter_factor_alignment_for_ticker(section_iv_raw, ticker)
        
        # Section V: Macro & geopolitical - KEEP AS-IS
        section_v = _find_section_by_prefix(sections, "V. MACRO")
        
        # Section VI: Sector rotation - FILTER to ticker's sector + related
        section_vi_raw = _find_section_by_prefix(sections, "VI. SECTOR")
        section_vi = extract_ticker_sector_from_rotation(section_vi_raw, ticker)
        
        # Section VII: Key global themes - KEEP AS-IS
        section_vii = _find_section_by_prefix(sections, "VII. KEY")
        
        # Section VIII: Macro risk factors - KEEP AS-IS
        section_viii = _find_section_by_prefix(sections, "VIII. MACRO RISK")
        
        # Reconstruct filtered packet
        header_match = re.search(r'^# SCANNER CONTEXT PACKET:.*?\n.*?Date:.*?\n', scanner_context, re.MULTILINE)
        header = header_match.group(0) if header_match else f"# SCANNER CONTEXT PACKET: {ticker}\n\n"
        
        filtered_sections = []
        if section_i:
            filtered_sections.append(f"## I. TICKER-SPECIFIC SCANNER THESIS\n{section_i}")
        if section_ii:
            filtered_sections.append(f"## II. STRUCTURED LIVE DATA (GROUND TRUTH)\n{section_ii}")
        if section_iii:
            filtered_sections.append(f"## III. SMART MONEY & FLOW SIGNALS\n{section_iii}")
        if section_iv:
            filtered_sections.append(f"## IV. FACTOR ALIGNMENT & DRIFT\n{section_iv}")
        if section_v:
            filtered_sections.append(f"## V. MACRO & GEOPOLITICAL CONTEXT\n{section_v}")
        if section_vi:
            filtered_sections.append(f"## VI. SECTOR ROTATION & MARKET REGIME\n{section_vi}")
        if section_vii:
            filtered_sections.append(f"## VII. KEY GLOBAL THEMES\n{section_vii}")
        if section_viii:
            filtered_sections.append(f"## VIII. MACRO RISK FACTORS\n{section_viii}")
        
        return header + "\n".join(filtered_sections)
    
    except Exception as e:
        logger.warning(f"Failed to filter scanner context for {ticker}: {e}")
        # Fallback: return original context
        return scanner_context


def _find_section_by_prefix(sections: dict[str, str], prefix: str) -> str:
    """Find a section by prefix match (handles variable-length titles)."""
    for key, value in sections.items():
        if key.startswith(prefix):
            return value
    return ""


def _split_scanner_sections(scanner_context: str) -> dict[str, str]:
    """Split scanner context into sections by ## headers."""
    sections = {}
    
    # Pattern: ## followed by roman numeral and title
    # Include hyphens in title to match "TICKER-SPECIFIC" etc.
    pattern = r'##\s+((?:I{1,3}|IV|V|VI{1,3})\.\s+[A-Z\s&()\-]+)'
    
    matches = list(re.finditer(pattern, scanner_context))
    
    for i, match in enumerate(matches):
        section_title = match.group(1).strip()
        start = match.end()
        
        # End is either the next section or end of string
        end = matches[i + 1].start() if i + 1 < len(matches) else len(scanner_context)
        
        section_content = scanner_context[start:end].strip()
        sections[section_title] = section_content
    
    return sections


def _filter_structured_data(section_text: str, ticker: str) -> str:
    """Filter Section II: Structured live data."""
    if not section_text:
        return section_text
    
    # Split into subsections
    subsections = {}
    
    # Look for ### subsection headers
    subsection_pattern = r'###\s+([^\n]+)'
    matches = list(re.finditer(subsection_pattern, section_text))
    
    for i, match in enumerate(matches):
        subsection_title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        subsection_content = section_text[start:end].strip()
        subsections[subsection_title] = subsection_content
    
    # Keep commodity prices and FX rates as-is (small)
    commodity_section = subsections.get("Commodity Prices", "")
    fx_section = subsections.get("FX Rates", "")

    # Filter earnings calendar
    earnings_raw = subsections.get("Earnings Calendar (7d lookback, 14d lookahead)", "")
    earnings_filtered = filter_earnings_calendar(earnings_raw, ticker, top_n_sector=10, top_n_overall=10)

    # Filter economic calendar
    econ_raw = subsections.get("Economic Calendar (7d lookback, 14d lookahead)", "")
    econ_filtered = filter_economic_calendar(econ_raw, max_events=10)

    # Reconstruct section — known subsections first, then pass through any others unchanged
    # (e.g. a "Recent News" subsection added by a scanner agent is preserved as-is)
    known_subsections = {
        "Commodity Prices",
        "FX Rates",
        "Earnings Calendar (7d lookback, 14d lookahead)",
        "Economic Calendar (7d lookback, 14d lookahead)",
    }

    filtered_parts = []
    if commodity_section:
        filtered_parts.append(f"### Commodity Prices\n{commodity_section}")
    if fx_section:
        filtered_parts.append(f"### FX Rates\n{fx_section}")
    if earnings_filtered:
        filtered_parts.append(f"### Earnings Calendar (Filtered: Ticker + Top 10 Same Sector)\n{earnings_filtered}")
    if econ_filtered:
        filtered_parts.append(f"### Economic Calendar (Top 10 High-Importance Events)\n{econ_filtered}")

    for title, content in subsections.items():
        if title not in known_subsections and content:
            filtered_parts.append(f"### {title}\n{content}")

    return "\n\n".join(filtered_parts)


def filter_earnings_calendar(
    earnings_text: str, 
    ticker: str, 
    top_n_sector: int = 10,
    top_n_overall: int = 10
) -> str:
    """
    Extract ticker-specific earnings + top N in same sector + biggest N overall.
    
    Strategy:
    1. Find all lines mentioning the ticker symbol
    2. Extract sector information if available
    3. Get top N from same sector (by market cap indicators)
    4. Get biggest N overall for context
    
    Args:
        earnings_text: Full earnings calendar text
        ticker: Target ticker symbol
        top_n_sector: Number of top same-sector companies to include
        top_n_overall: Number of biggest overall companies to include
    
    Returns:
        Filtered earnings calendar (~300-500 tokens)
    """
    if not earnings_text or not ticker:
        return earnings_text
    
    ticker = ticker.upper()
    
    # Split into lines
    lines = earnings_text.split('\n')
    
    # Find ticker-specific lines
    ticker_lines = [line for line in lines if ticker in line.upper()]
    
    # Try to identify sector from ticker lines or context
    # This is heuristic - in production you'd use a proper sector lookup
    ticker_sector = _infer_sector_from_text(earnings_text, ticker)
    
    # Find same-sector companies (heuristic: look for sector keywords in lines)
    same_sector_lines = []
    if ticker_sector:
        sector_keywords = ticker_sector.lower().split()
        for line in lines:
            if ticker in line.upper():
                continue  # Already captured
            if any(keyword in line.lower() for keyword in sector_keywords):
                same_sector_lines.append(line)
    
    # Find large-cap companies (heuristic: look for "Mega Cap", "Large Cap", or well-known tickers)
    large_cap_indicators = ["mega cap", "large cap", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "BAC"]
    large_cap_lines = []
    for line in lines:
        if ticker in line.upper():
            continue
        if any(indicator in line for indicator in large_cap_indicators):
            large_cap_lines.append(line)
    
    # Combine and deduplicate
    filtered_lines = []
    
    # Add ticker lines first
    filtered_lines.extend(ticker_lines)
    
    # Add same-sector lines (up to top_n_sector)
    added_same_sector = 0
    for line in same_sector_lines:
        if line not in filtered_lines and added_same_sector < top_n_sector:
            filtered_lines.append(line)
            added_same_sector += 1
    
    # Add large-cap lines (up to top_n_overall)
    added_large_cap = 0
    for line in large_cap_lines:
        if line not in filtered_lines and added_large_cap < top_n_overall:
            filtered_lines.append(line)
            added_large_cap += 1
    
    # If we didn't get enough, just take first N lines as fallback
    if len(filtered_lines) < 5:
        filtered_lines = lines[:min(20, len(lines))]
    
    result = '\n'.join(filtered_lines)
    
    # Add summary note
    summary = f"[Filtered to {len(filtered_lines)} entries: {ticker} + same-sector + largest companies]\n\n{result}"
    
    return summary


def filter_economic_calendar(econ_text: str, max_events: int = 10) -> str:
    """
    Summarize economic calendar to most important events.
    
    Strategy:
    1. Keep all "High" importance events
    2. If under max_events, add "Medium" importance
    3. Sort by date and importance
    
    Args:
        econ_text: Full economic calendar text
        max_events: Maximum number of events to keep
    
    Returns:
        Filtered economic calendar (~300-500 tokens)
    """
    if not econ_text:
        return econ_text
    
    lines = econ_text.split('\n')
    
    # Categorize by importance
    high_importance = []
    medium_importance = []
    other_lines = []
    
    for line in lines:
        line_lower = line.lower()
        if 'high' in line_lower and ('importance' in line_lower or 'impact' in line_lower):
            high_importance.append(line)
        elif 'medium' in line_lower and ('importance' in line_lower or 'impact' in line_lower):
            medium_importance.append(line)
        # Keep key economic indicators even without explicit importance tags
        elif any(indicator in line_lower for indicator in ['fomc', 'cpi', 'gdp', 'unemployment', 'nfp', 'fed']):
            high_importance.append(line)
        else:
            other_lines.append(line)
    
    # Build filtered list
    filtered_lines = high_importance[:max_events]
    
    # If under max, add medium importance
    if len(filtered_lines) < max_events:
        remaining_slots = max_events - len(filtered_lines)
        filtered_lines.extend(medium_importance[:remaining_slots])
    
    # If still short and there are other lines, add them
    if len(filtered_lines) < 3 and other_lines:
        filtered_lines.extend(other_lines[:5])
    
    result = '\n'.join(filtered_lines) if filtered_lines else econ_text[:500]
    
    summary = f"[Filtered to {len(filtered_lines)} high-priority events]\n\n{result}"
    
    return summary


def extract_ticker_sector_from_rotation(sector_report: str, ticker: str) -> str:
    """
    Extract ticker's sector + related sector from sector rotation report.
    
    Strategy:
    1. Parse sector report (likely contains sector performance tables)
    2. Identify ticker's sector
    3. Return that sector + one related sector (if well-known relationship exists)
    
    Args:
        sector_report: Full sector rotation report
        ticker: Target ticker symbol
    
    Returns:
        Filtered sector report (~300-400 tokens)
    """
    if not sector_report or not ticker:
        return sector_report
    
    ticker = ticker.upper()
    
    # Infer ticker's sector from the report
    ticker_sector = _infer_sector_from_text(sector_report, ticker)
    
    if not ticker_sector:
        # Can't identify sector, return truncated version
        return sector_report[:1000] + "\n\n[Truncated - unable to identify ticker sector]"
    
    # Find related sector
    related_sectors = RELATED_SECTORS.get(ticker_sector, [])
    related_sector = related_sectors[0] if related_sectors else None
    
    # Extract sections mentioning ticker's sector or related sector
    lines = sector_report.split('\n')
    filtered_lines = []
    
    for line in lines:
        # Keep lines that mention the ticker's sector or related sector
        if ticker_sector.lower() in line.lower():
            filtered_lines.append(line)
        elif related_sector and related_sector.lower() in line.lower():
            filtered_lines.append(line)
        # Also keep header lines and summary lines
        elif line.startswith('#') or line.startswith('##') or 'summary' in line.lower():
            filtered_lines.append(line)
    
    result = '\n'.join(filtered_lines) if filtered_lines else sector_report[:800]
    
    summary_note = f"[Filtered to {ticker_sector}"
    if related_sector:
        summary_note += f" + related sector: {related_sector}"
    summary_note += "]\n\n"
    
    return summary_note + result


def filter_smart_money_for_ticker(smart_money_report: str, ticker: str) -> str:
    """
    Extract ticker-specific smart money signals.
    
    Strategy:
    1. Look for ticker mentions in the report
    2. Extract those sections
    3. If ticker not mentioned, keep summary only (first paragraph)
    
    Args:
        smart_money_report: Full smart money report
        ticker: Target ticker symbol
    
    Returns:
        Filtered smart money report (~300-400 tokens)
    """
    if not smart_money_report or not ticker:
        return smart_money_report
    
    ticker = ticker.upper()

    metadata_block, smart_money_body = _extract_smart_money_metadata_block(
        smart_money_report
    )
    
    # Split into paragraphs
    paragraphs = smart_money_body.split('\n\n') if smart_money_body else []
    
    # Infer the ticker's sector so we can include sector-level signals even when
    # the ticker is not named directly.
    ticker_sector = _infer_sector_from_text(smart_money_body or smart_money_report, ticker)
    related_sectors = RELATED_SECTORS.get(ticker_sector or "", [])

    ticker_paragraphs: list[str] = []
    sector_paragraphs: list[str] = []
    market_paragraphs: list[str] = []  # broad market / macro signals

    market_keywords = ["market", "broad", "all sectors", "overall", "macro", "index", "s&p", "nasdaq", "dow"]

    for para in paragraphs:
        para_lower = para.lower()
        if ticker in para.upper():
            ticker_paragraphs.append(para)
        elif ticker_sector and ticker_sector.lower() in para_lower:
            sector_paragraphs.append(para)
        elif any(rs.lower() in para_lower for rs in related_sectors):
            sector_paragraphs.append(para)
        elif any(kw in para_lower for kw in market_keywords):
            market_paragraphs.append(para)

    if ticker_paragraphs:
        combined = ticker_paragraphs + sector_paragraphs + market_paragraphs[:2]
        result = '\n\n'.join(combined)
        return _prepend_smart_money_metadata(
            metadata_block,
            f"[Filtered to {ticker}-specific and related sector signals]\n\n{result}",
        )

    # Ticker not found — include sector and market-wide context so the analyst
    # still receives relevant signals that affect this ticker indirectly.
    fallback = sector_paragraphs + market_paragraphs[:3]
    if fallback:
        result = '\n\n'.join(fallback)
        label = f"[No {ticker}-specific signals found"
        if ticker_sector:
            label += f". Including {ticker_sector} sector and market-wide signals"
        label += ".]"
        return _prepend_smart_money_metadata(metadata_block, f"{label}\n\n{result}")

    # Last resort: first paragraph
    if paragraphs:
        return _prepend_smart_money_metadata(
            metadata_block,
            f"[No {ticker}-specific signals found. General summary:]\n\n{paragraphs[0]}",
        )

    return smart_money_report


def _extract_smart_money_metadata_block(report: str) -> tuple[str, str]:
    """Split leading provenance metadata from the smart-money narrative body."""
    if not report:
        return "", ""

    lines = report.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    metadata_lines: list[str] = []
    body_start = 0

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped and metadata_lines:
            body_start = idx + 1
            break
        if (
            stripped.startswith("Source:")
            or stripped.startswith("Scan Date:")
            or stripped.startswith("[Source:")
        ):
            metadata_lines.append(stripped)
            body_start = idx + 1
            continue
        break

    metadata_block = "\n".join(metadata_lines).strip()
    body = "\n".join(lines[body_start:]).strip() if metadata_lines else report.strip()
    return metadata_block, body


def _prepend_smart_money_metadata(metadata_block: str, body: str) -> str:
    """Re-attach smart-money provenance metadata ahead of filtered content."""
    body = (body or "").strip()
    if metadata_block and body:
        return f"{metadata_block}\n\n{body}"
    return metadata_block or body


def filter_factor_alignment_for_ticker(factor_report: str, ticker: str) -> str:
    """
    Extract ticker-specific factor alignment.
    
    Strategy:
    1. Parse factor alignment report (likely has ticker candidates)
    2. Find ticker's entry
    3. Return ticker's factors + summary of macro factor regime
    
    Args:
        factor_report: Full factor alignment report
        ticker: Target ticker symbol
    
    Returns:
        Filtered factor alignment (~200-300 tokens)
    """
    if not factor_report or not ticker:
        return factor_report
    
    ticker = ticker.upper()
    
    # Split into sections
    sections = factor_report.split('\n\n')

    # Infer sector so we can include sector-level factor signals.
    ticker_sector = _infer_sector_from_text(factor_report, ticker)
    related_sectors = RELATED_SECTORS.get(ticker_sector or "", [])

    market_keywords = ["summary", "regime", "macro", "factor", "overall", "market", "broad", "index"]

    ticker_sections: list[str] = []
    sector_sections: list[str] = []
    summary_sections: list[str] = []

    for section in sections:
        section_lower = section.lower()
        if ticker in section.upper():
            ticker_sections.append(section)
        elif ticker_sector and ticker_sector.lower() in section_lower:
            sector_sections.append(section)
        elif any(rs.lower() in section_lower for rs in related_sectors):
            sector_sections.append(section)
        elif any(keyword in section_lower for keyword in market_keywords):
            summary_sections.append(section)

    # Combine: ticker-specific → sector → market summaries
    filtered_sections = ticker_sections + sector_sections + summary_sections[:2]

    if filtered_sections:
        result = '\n\n'.join(filtered_sections)
        label = f"[Filtered to {ticker}-specific factors"
        if not ticker_sections and ticker_sector:
            label += f". Including {ticker_sector} sector context"
        label += "]"
        return f"{label}\n\n{result}"

    # Fallback: first part of report
    truncated = factor_report[:800]
    return f"[No {ticker}-specific factor data found. Showing general context:]\n\n{truncated}"


def _infer_sector_from_text(text: str, ticker: str) -> str | None:
    """
    Heuristic to infer a ticker's sector from text.
    
    Looks for sector keywords near ticker mentions.
    """
    ticker = ticker.upper()
    
    # Standard sector names
    sectors = [
        "Energy", "Materials", "Industrials", "Consumer Discretionary",
        "Consumer Staples", "Health Care", "Financials", "Information Technology",
        "Technology", "Communication Services", "Utilities", "Real Estate"
    ]
    
    # Find context around ticker mentions
    lines = text.split('\n')
    for line in lines:
        if ticker in line.upper():
            # Check this line and nearby lines for sector keywords
            for sector in sectors:
                if sector.lower() in line.lower():
                    return sector
    
    # No sector found
    return None
