"""Helpers for deterministic packet assembly and compact debate context."""

from __future__ import annotations


def _compact_lines(text: str, *, max_lines: int = 8, max_chars: int = 1600) -> str:
    lines: list[str] = []
    total = 0
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        line_len = len(line) + 1
        if total + line_len > max_chars:
            break
        lines.append(line)
        total += line_len
        if len(lines) >= max_lines:
            break
    return "\n".join(lines).strip()


def _format_market_structured(structured: object) -> str:
    if not isinstance(structured, dict):
        return ""
    key_levels = structured.get("key_levels") or []
    if not isinstance(key_levels, list):
        key_levels = []
    key_metrics = structured.get("key_metrics") or {}
    if not isinstance(key_metrics, dict):
        key_metrics = {}
    lines = [
        f"- status: {structured.get('status', '')}",
        f"- contract_version: {structured.get('contract_version', '')}",
        f"- macro_regime: {structured.get('macro_regime', '')}",
        f"- claim_count: {structured.get('claim_count', '')}",
        f"- key_levels: {', '.join(str(level) for level in key_levels[:3])}",
        f"- numeric_mentions: {key_metrics.get('numeric_mentions', '')}",
        f"- summary_table_rows: {key_metrics.get('summary_table_rows', '')}",
    ]
    return "\n".join(line for line in lines if line.split(":", 1)[1].strip())


def _format_fundamentals_structured(structured: object) -> str:
    if not isinstance(structured, dict):
        return ""
    key_metrics = structured.get("key_metrics") or {}
    if not isinstance(key_metrics, dict):
        key_metrics = {}
    prefetch = structured.get("prefetch") or {}
    if not isinstance(prefetch, dict):
        prefetch = {}
    present_sections = prefetch.get("present_sections") or []
    if not isinstance(present_sections, list):
        present_sections = []
    error_sections = prefetch.get("error_sections") or []
    if not isinstance(error_sections, list):
        error_sections = []
    lines = [
        f"- status: {structured.get('status', '')}",
        f"- contract_version: {structured.get('contract_version', '')}",
        f"- macro_regime: {structured.get('macro_regime', '')}",
        f"- bullet_count: {structured.get('bullet_count', '')}",
        f"- numeric_mentions: {key_metrics.get('numeric_mentions', '')}",
        f"- summary_table_rows: {key_metrics.get('summary_table_rows', '')}",
        f"- present_sections: {', '.join(str(item) for item in present_sections[:4])}",
        f"- error_sections: {', '.join(str(item) for item in error_sections[:4])}",
    ]
    return "\n".join(line for line in lines if line.split(":", 1)[1].strip())


def _has_value_after_colon(line: str) -> bool:
    """Return True if the line has a non-empty value after its first colon."""
    parts = line.split(":", 1)
    return len(parts) == 2 and bool(parts[1].strip())


def _format_sentiment_structured(structured: object) -> str:
    if not isinstance(structured, dict):
        return ""
    key_metrics = structured.get("key_metrics") or {}
    if not isinstance(key_metrics, dict):
        key_metrics = {}
    lines = [
        f"- status: {structured.get('status', '')}",
        f"- contract_version: {structured.get('contract_version', '')}",
        f"- sentiment_direction: {structured.get('sentiment_direction', '')}",
        f"- claim_count: {structured.get('claim_count', '')}",
        f"- numeric_mentions: {key_metrics.get('numeric_mentions', '')}",
        f"- source_mentions: {key_metrics.get('source_mentions', '')}",
    ]
    return "\n".join(line for line in lines if _has_value_after_colon(line))



def build_research_packet(state: dict) -> str:
    """Return the canonical deterministic analyst packet for downstream nodes."""
    sections: list[str] = []

    scanner_context_packet = _compact_lines(
        str(state.get("scanner_context_packet") or ""),
        max_lines=10,
        max_chars=2000,
    )
    if scanner_context_packet:
        sections.append(f"## Scanner Context (Phase 1)\n{scanner_context_packet}")

    market_structured = _format_market_structured(state.get("market_report_structured"))
    if market_structured:
        sections.append(f"## Market Structured Contract\n{market_structured}")

    fundamentals_structured = _format_fundamentals_structured(
        state.get("fundamentals_report_structured")
    )
    if fundamentals_structured:
        sections.append(f"## Fundamentals Structured Contract\n{fundamentals_structured}")

    sentiment_structured = _format_sentiment_structured(state.get("sentiment_report_structured"))
    if sentiment_structured:
        sections.append(f"## Sentiment Structured Contract\n{sentiment_structured}")

    block_specs = [
        ("## Market Report", state.get("market_report"), 10, 2200),
        ("## Sentiment Report", state.get("sentiment_report"), 8, 1600),
        ("## News Report", state.get("news_report"), 10, 2200),
        ("## Fundamentals Report", state.get("fundamentals_report"), 10, 2200),
        ("## Macro Regime Report", state.get("macro_regime_report"), 6, 1000),
    ]
    for header, raw_value, max_lines, max_chars in block_specs:
        compact = _compact_lines(str(raw_value or ""), max_lines=max_lines, max_chars=max_chars)
        if compact:
            sections.append(f"{header}\n{compact}")

    return "\n\n".join(sections).strip()


def build_investment_debate_summary(debate_state: dict) -> str:
    """Build a compact bull/bear debate summary from per-round summary points."""
    bull_summary = str(debate_state.get("current_bull_summary") or "").strip()
    bear_summary = str(debate_state.get("current_bear_summary") or "").strip()

    sections = []
    if bull_summary:
        sections.append(f"### Bull Analyst Points\n{bull_summary}")
    if bear_summary:
        sections.append(f"### Bear Analyst Points\n{bear_summary}")
    return "\n\n".join(sections).strip()


def build_risk_debate_summary(debate_state: dict) -> str:
    """Build a compact risk summary from latest analyst response snippets."""
    aggressive = str(debate_state.get("current_aggressive_response") or "").strip()
    conservative = str(debate_state.get("current_conservative_response") or "").strip()
    neutral = str(debate_state.get("current_neutral_response") or "").strip()

    sections = []
    if aggressive:
        sections.append(f"### Aggressive Analyst Points\n{aggressive}")
    if conservative:
        sections.append(f"### Conservative Analyst Points\n{conservative}")
    if neutral:
        sections.append(f"### Neutral Analyst Points\n{neutral}")
    return "\n\n".join(sections).strip()


def get_investment_debate_summary(state: dict) -> str:
    debate_state = state.get("investment_debate_state") or {}
    summary = str(debate_state.get("summary") or "").strip()
    if summary:
        return summary
    compact_summary = build_investment_debate_summary(debate_state)
    if compact_summary:
        return compact_summary
    return str(debate_state.get("history") or "").strip()


def get_risk_debate_summary(state: dict) -> str:
    debate_state = state.get("risk_debate_state") or {}
    summary = str(debate_state.get("summary") or "").strip()
    if summary:
        return summary
    compact_summary = build_risk_debate_summary(debate_state)
    if compact_summary:
        return compact_summary
    return str(debate_state.get("history") or "").strip()
