"""Helpers for choosing compressed prompt context when summaries exist."""

from __future__ import annotations


def build_research_packet(state: dict) -> str:
    """Return a compact analyst packet when available, otherwise raw reports."""
    summary = str(state.get("research_packet_summary") or "").strip()
    if summary:
        return summary

    parts = []
    labeled_reports = (
        ("Scanner Context (Phase 1)", state.get("scanner_context_packet", "")),
        ("Market Research Report", state.get("market_report", "")),
        ("Social Media Sentiment Report", state.get("sentiment_report", "")),
        ("Latest World Affairs Report", state.get("news_report", "")),
        ("Company Fundamentals Report", state.get("fundamentals_report", "")),
        ("Macro Regime Report", state.get("macro_regime_report", "")),
    )
    for label, content in labeled_reports:
        content = str(content or "").strip()
        if content:
            parts.append(f"{label}: {content}")
    return "\n\n".join(parts)


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
