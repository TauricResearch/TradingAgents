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


def get_investment_debate_summary(state: dict) -> str:
    debate_state = state.get("investment_debate_state") or {}
    summary = str(debate_state.get("summary") or "").strip()
    if summary:
        return summary
    return str(debate_state.get("history") or "").strip()


def get_risk_debate_summary(state: dict) -> str:
    debate_state = state.get("risk_debate_state") or {}
    summary = str(debate_state.get("summary") or "").strip()
    if summary:
        return summary
    return str(debate_state.get("history") or "").strip()
