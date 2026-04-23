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


def _format_news_structured(structured: object) -> str:
    """Format news structured contract for downstream context."""
    if not isinstance(structured, dict):
        return ""
    key_metrics = structured.get("key_metrics") or {}
    if not isinstance(key_metrics, dict):
        key_metrics = {}
    lines = [
        f"- status: {structured.get('status', '')}",
        f"- contract_version: {structured.get('contract_version', '')}",
        f"- claim_count: {key_metrics.get('claim_count', '')}",
        f"- summary_rows: {key_metrics.get('summary_rows', '')}",
        f"- evidence_ids: {key_metrics.get('evidence_ids', '')}",
        f"- removed_claims: {key_metrics.get('removed_claims', '')}",
        f"- below_min_claims: {key_metrics.get('below_min_claims', '')}",
    ]
    return "\n".join(line for line in lines if _has_value_after_colon(line))




def build_debate_evidence_brief(state: dict) -> str:
    """Build a compact evidence brief for debaters from structured contracts.

    This is a deterministic extraction (no LLM call) that replaces the full
    research packet in debater prompts, cutting input from ~5000ch to ~1500ch.
    The Research Manager still receives the full packet via build_research_packet().
    """
    sections: list[str] = []

    # Scanner ground truth (verified prices, FX, dates)
    scanner = _compact_lines(
        str(state.get("scanner_graph_context_text") or ""),
        max_lines=6,
        max_chars=800,
    )
    if scanner:
        role_guidance = "Treat scanner graph context as the compact ground-truth scanner evidence block for this ticker."
        sections.append(f"## Ground Truth\n\n{role_guidance}\n\n{scanner}")

    # Market structured: macro regime + key levels
    market_s = state.get("market_report_structured")
    if isinstance(market_s, dict):
        lines = []
        macro = market_s.get("macro_regime", "")
        if macro:
            lines.append(f"- Macro regime: {macro}")
        key_levels = market_s.get("key_levels") or []
        if isinstance(key_levels, list) and key_levels:
            lines.append(f"- Key levels: {', '.join(str(lv) for lv in key_levels[:4])}")
        claim_count = market_s.get("claim_count", "")
        if claim_count:
            lines.append(f"- Market claims: {claim_count}")
        if lines:
            sections.append("## Market\n" + "\n".join(lines))

    # Fundamentals structured: excerpt + section availability
    fund_s = state.get("fundamentals_report_structured")
    if isinstance(fund_s, dict):
        lines = []
        excerpt = str(fund_s.get("report_excerpt") or "").strip()
        if excerpt:
            lines.append(excerpt)
        prefetch = fund_s.get("prefetch") or {}
        if isinstance(prefetch, dict):
            present = prefetch.get("present_sections") or []
            errors = prefetch.get("error_sections") or []
            if present:
                lines.append(f"- Sections available: {', '.join(str(s) for s in present[:5])}")
            if errors:
                lines.append(f"- Sections with errors: {', '.join(str(s) for s in errors[:3])}")
        if lines:
            sections.append("## Fundamentals\n" + "\n".join(lines))

    # Sentiment structured: direction + claim count
    sent_s = state.get("sentiment_report_structured")
    if isinstance(sent_s, dict):
        lines = []
        direction = sent_s.get("sentiment_direction", "")
        if direction:
            lines.append(f"- Sentiment direction: {direction}")
        claim_count = sent_s.get("claim_count", "")
        if claim_count:
            lines.append(f"- Sentiment claims: {claim_count}")
        if lines:
            sections.append("## Sentiment\n" + "\n".join(lines))
    
    # News structured: status + claim metrics (exclude claim text)
    news_s = state.get("news_report_structured")
    if isinstance(news_s, dict):
        lines = []
        status = news_s.get("status", "")
        if status:
            lines.append(f"- News status: {status}")
        key_metrics = news_s.get("key_metrics") or {}
        if isinstance(key_metrics, dict):
            claim_count = key_metrics.get("claim_count")
            if claim_count is not None:
                lines.append(f"- News claims: {claim_count}")
            evidence_ids = key_metrics.get("evidence_ids")
            if evidence_ids is not None:
                lines.append(f"- Evidence IDs: {evidence_ids}")
            removed_claims = key_metrics.get("removed_claims")
            if removed_claims is not None:
                lines.append(f"- Removed claims: {removed_claims}")
        if lines:
            sections.append("## News\n" + "\n".join(lines))

    # Macro regime report (compact)
    macro_report = _compact_lines(
        str(state.get("macro_regime_report") or ""),
        max_lines=4,
        max_chars=600,
    )
    if macro_report:
        sections.append(f"## Macro\n{macro_report}")

    return "\n\n".join(sections).strip()


def build_research_packet(state: dict) -> str:
    """Return the canonical deterministic analyst packet for downstream nodes."""
    sections: list[str] = []

    scanner_graph_context = _compact_lines(
        str(state.get("scanner_graph_context_text") or ""),
        max_lines=10,
        max_chars=2000,
    )
    if scanner_graph_context:
        sections.append(f"## Scanner Graph Context\n{scanner_graph_context}")

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

    news_structured = _format_news_structured(state.get("news_report_structured"))
    if news_structured:
        sections.append(f"## News Structured Contract\n{news_structured}")
    
    # Check if news has usable evidence for gating raw report inclusion
    news_report_structured = state.get("news_report_structured")
    news_status = str(news_report_structured.get("status") or "").strip() if isinstance(news_report_structured, dict) else ""
    key_metrics = news_report_structured.get("key_metrics") or {} if isinstance(news_report_structured, dict) else {}
    claim_count = key_metrics.get("claim_count", 0) if isinstance(key_metrics, dict) else 0
    news_has_usable_evidence = news_status == "completed" and claim_count > 0

    # Build raw report blocks (gate news based on usability)
    block_specs = [
        ("## Market Report", state.get("market_report"), 10, 2200),
        ("## Sentiment Report", state.get("sentiment_report"), 8, 1600),
        ("## News Report", state.get("news_report") if news_has_usable_evidence else None, 10, 2200),
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
