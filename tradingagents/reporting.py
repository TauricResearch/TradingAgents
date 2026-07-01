"""Reusable report-tree writer shared by the CLI and the programmatic API.

Writes a run's per-section markdown (analysts, research, trading, risk,
portfolio) plus a consolidated ``complete_report.md`` under ``save_path``. The
CLI and ``TradingAgentsGraph.save_reports`` both call this, so a headless / API
run produces the same on-disk report tree a CLI run does.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_AUDIT_KEYS = (
    "evidence_ledger",
    "citation_verification",
    "quantitative_anchors",
    "math_guardrail_events",
    "evidence_warnings",
    "evidence_strict_mode",
    "evidence_strict_blocked",
    "evidence_decision_status",
    "evidence_actionable",
    "evidence_blocking_reasons",
    "original_final_trade_decision",
)


def build_evidence_audit(final_state: dict) -> dict[str, Any]:
    """Return the evidence audit payload carried by a completed run."""
    return {
        "evidence_ledger": _jsonable(final_state.get("evidence_ledger", {"items": []})),
        "citation_verification": _jsonable(final_state.get("citation_verification")),
        "quantitative_anchors": _jsonable(final_state.get("quantitative_anchors", [])),
        "math_guardrail_events": _jsonable(final_state.get("math_guardrail_events", [])),
        "evidence_warnings": _jsonable(final_state.get("evidence_warnings", [])),
        "evidence_strict_mode": _jsonable(final_state.get("evidence_strict_mode")),
        "evidence_strict_blocked": _jsonable(
            final_state.get("evidence_strict_blocked", False)
        ),
        "evidence_decision_status": _jsonable(
            final_state.get("evidence_decision_status")
        ),
        "evidence_actionable": _jsonable(final_state.get("evidence_actionable")),
        "evidence_blocking_reasons": _jsonable(
            final_state.get("evidence_blocking_reasons", [])
        ),
        "original_final_trade_decision": _jsonable(
            final_state.get("original_final_trade_decision")
        ),
    }


def write_report_tree(final_state: dict, ticker: str, save_path) -> Path:
    """Save a completed run's reports to ``save_path``; return the complete-report path."""
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    # 1. Analysts
    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if final_state.get("market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market.md").write_text(final_state["market_report"], encoding="utf-8")
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "sentiment.md").write_text(final_state["sentiment_report"], encoding="utf-8")
        analyst_parts.append(("Sentiment Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(final_state["news_report"], encoding="utf-8")
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "fundamentals.md").write_text(final_state["fundamentals_report"], encoding="utf-8")
        analyst_parts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    # 2. Research
    if final_state.get("investment_debate_state"):
        research_dir = save_path / "2_research"
        debate = final_state["investment_debate_state"]
        research_parts = []
        if debate.get("bull_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bull.md").write_text(debate["bull_history"], encoding="utf-8")
            research_parts.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(debate["bear_history"], encoding="utf-8")
            research_parts.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(debate["judge_decision"], encoding="utf-8")
            research_parts.append(("Research Manager", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{content}")

    # 3. Trading
    if final_state.get("trader_investment_plan"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(final_state["trader_investment_plan"], encoding="utf-8")
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}")

    # 4. Risk Management
    if final_state.get("risk_debate_state"):
        risk_dir = save_path / "4_risk"
        risk = final_state["risk_debate_state"]
        risk_parts = []
        if risk.get("aggressive_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "aggressive.md").write_text(risk["aggressive_history"], encoding="utf-8")
            risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "conservative.md").write_text(risk["conservative_history"], encoding="utf-8")
            risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "neutral.md").write_text(risk["neutral_history"], encoding="utf-8")
            risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

    # 5. Portfolio Manager
    risk = final_state.get("risk_debate_state") or {}
    portfolio_decision = final_state.get("final_trade_decision") or risk.get("judge_decision")
    if portfolio_decision:
        portfolio_dir = save_path / "5_portfolio"
        portfolio_dir.mkdir(exist_ok=True)
        (portfolio_dir / "decision.md").write_text(portfolio_decision, encoding="utf-8")
        sections.append(f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{portfolio_decision}")

    evidence_audit = build_evidence_audit(final_state)
    if _has_evidence_audit(final_state):
        evidence_dir = save_path / "6_evidence"
        evidence_dir.mkdir(exist_ok=True)
        audit_markdown = _render_evidence_audit(evidence_audit)
        (evidence_dir / "audit.md").write_text(audit_markdown, encoding="utf-8")
        (save_path / "evidence_audit.json").write_text(
            json.dumps(evidence_audit, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        sections.append(f"## VI. Evidence Audit\n\n{audit_markdown}")

    # Write consolidated report
    header = f"# Trading Analysis Report: {ticker}\n\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    (save_path / "complete_report.md").write_text(header + "\n\n".join(sections), encoding="utf-8")
    return save_path / "complete_report.md"


def _has_evidence_audit(final_state: dict) -> bool:
    return any(_audit_value_present(final_state.get(key)) for key in _AUDIT_KEYS)


def _audit_value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return bool(value.get("items")) if set(value) == {"items"} else bool(value)
    if isinstance(value, (list, tuple, set, str)):
        return bool(value)
    return True


def _render_evidence_audit(audit: dict[str, Any]) -> str:
    ledger_items = audit["evidence_ledger"].get("items", []) if isinstance(audit["evidence_ledger"], dict) else []
    citation = audit["citation_verification"]
    anchors = audit["quantitative_anchors"] or []
    guardrail_events = audit["math_guardrail_events"] or []
    warnings = audit["evidence_warnings"] or []
    blocking_reasons = audit.get("evidence_blocking_reasons") or []
    strict_mode = audit.get("evidence_strict_mode") or "warn"
    strict_result = "blocked" if audit.get("evidence_strict_blocked") else "not blocked"
    decision_status = audit.get("evidence_decision_status") or "unknown"
    actionable = audit.get("evidence_actionable")
    actionable_label = "unknown" if actionable is None else str(bool(actionable)).lower()
    original_decision_label = (
        "captured" if audit.get("original_final_trade_decision") else "not captured"
    )
    evidence_links = _evidence_links(ledger_items)

    parts = [
        f"**Evidence Ledger Items**: {len(ledger_items)}",
        "",
        f"**Citation Verification**: {_citation_status(citation)}",
        "",
        f"**Quantitative Anchors**: {len(anchors)}",
        "",
        f"**Math Guardrail Events**: {len(guardrail_events)}",
        "",
        f"**Evidence Warnings**: {len(warnings)}",
        "",
        f"**Evidence Strict Status**: {strict_mode} / {strict_result}",
        "",
        f"**Evidence Decision Status**: {decision_status}",
        "",
        f"**Evidence Actionable**: {actionable_label}",
        "",
        f"**Original Final Trade Decision**: {original_decision_label}",
    ]
    if ledger_items:
        ids = [item.get("evidence_id") for item in ledger_items if isinstance(item, dict) and item.get("evidence_id")]
        if ids:
            parts.extend(["", f"- Evidence IDs: {', '.join(ids)}"])
    if isinstance(citation, dict) and citation.get("warnings"):
        parts.extend(["", "- Citation warnings: " + "; ".join(citation["warnings"])])
    parts.extend(["", _render_evidence_ledger_section(ledger_items, evidence_links)])
    parts.extend(["", _render_quantitative_anchors_section(anchors, evidence_links)])
    parts.extend(["", _render_math_guardrail_events_section(guardrail_events, evidence_links)])
    if warnings:
        parts.extend(["", "- Evidence warnings: " + "; ".join(str(warning) for warning in warnings)])
    if blocking_reasons:
        parts.extend(["", "- Blocking reasons: " + "; ".join(str(reason) for reason in blocking_reasons)])
    return "\n".join(parts)


def _citation_status(citation: Any) -> str:
    if not isinstance(citation, dict):
        return "Not run"
    return "Passed" if citation.get("passed") else "Failed"


def _render_evidence_ledger_section(
    ledger_items: list[Any],
    evidence_links: dict[str, tuple[str, str]],
) -> str:
    parts = ["### Evidence Ledger"]
    if not ledger_items:
        return "\n\n".join([*parts, "None."])

    rows = [
        "| Evidence ID | Title | Source | As-of Date | Summary |",
        "| --- | --- | --- | --- | --- |",
    ]
    detail_parts = []
    for item in ledger_items:
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "unknown")
        heading_text, anchor = evidence_links[evidence_id]
        source = item.get("source", "")
        payload = item.get("payload")
        summary = _payload_summary(payload, source=source)
        rows.append(
            " | ".join(
                [
                    f"| {_evidence_link(evidence_id, anchor)}",
                    _markdown_table_cell(item.get("title", "")),
                    _markdown_table_cell(source),
                    _markdown_table_cell(item.get("as_of_date", "")),
                    f"{_markdown_table_cell(summary)} |",
                ]
            )
        )
        detail_parts.extend(
            [
                f"#### {heading_text}",
                "",
                f"- Source: {_markdown_text(source)}",
                f"- As-of Date: {_markdown_text(item.get('as_of_date', ''))}",
                f"- Summary: {_markdown_text(summary) if summary else 'None.'}",
            ]
        )

    if len(rows) == 2:
        return "\n\n".join([*parts, "None."])
    return "\n\n".join([*parts, "\n".join(rows), "\n".join(detail_parts)])


def _render_quantitative_anchors_section(
    anchors: list[Any],
    evidence_links: dict[str, tuple[str, str]],
) -> str:
    parts = ["### Quantitative Anchors"]
    if not anchors:
        return "\n\n".join([*parts, "None."])

    rows = [
        "| Anchor ID | Symbol | Current Price | As-of Date | Evidence ID |",
        "| --- | --- | --- | --- | --- |",
    ]
    for anchor in anchors:
        if not isinstance(anchor, dict):
            continue
        evidence_id = anchor.get("evidence_id")
        evidence_cell = _evidence_reference_link(str(evidence_id), evidence_links) if evidence_id else ""
        rows.append(
            " | ".join(
                [
                    f"| {_markdown_table_cell(anchor.get('anchor_id', ''))}",
                    _markdown_table_cell(anchor.get("symbol", "")),
                    _markdown_table_cell(anchor.get("current_price", "")),
                    _markdown_table_cell(anchor.get("as_of_date", "")),
                    f"{evidence_cell} |",
                ]
            )
        )
    if len(rows) == 2:
        return "\n\n".join([*parts, "None."])
    return "\n\n".join([*parts, "\n".join(rows)])


def _render_math_guardrail_events_section(
    events: list[Any],
    evidence_links: dict[str, tuple[str, str]],
) -> str:
    parts = ["### Math Guardrail Events"]
    if not events:
        return "\n\n".join([*parts, "None."])

    rows = [
        "| Rule ID | Status | Message / Action / Evidence |",
        "| --- | --- | --- |",
    ]
    for event in events:
        if not isinstance(event, dict):
            continue
        detail_items = []
        if event.get("message"):
            detail_items.append(_markdown_table_cell(event["message"]))
        if event.get("action"):
            detail_items.append(f"action={_markdown_table_cell(event['action'])}")
        if event.get("evidence_id"):
            detail_items.append(
                _evidence_reference_link(str(event["evidence_id"]), evidence_links)
            )
        rows.append(
            " | ".join(
                [
                    f"| {_markdown_table_cell(event.get('rule_id', ''))}",
                    _markdown_table_cell(event.get("status", "")),
                    f"{'; '.join(detail_items)} |",
                ]
            )
        )
    if len(rows) == 2:
        return "\n\n".join([*parts, "None."])
    return "\n\n".join([*parts, "\n".join(rows)])


def _payload_summary(payload: Any, *, source: Any = None) -> str:
    if not isinstance(payload, dict):
        return ""

    if source == "verified_market_snapshot":
        latest_ohlcv = payload.get("latest_ohlcv")
        latest_ohlcv = latest_ohlcv if isinstance(latest_ohlcv, dict) else {}
        preferred_values = {
            "latest_date": payload.get("latest_date"),
            "Close": latest_ohlcv.get("Close", payload.get("Close")),
            "Volume": latest_ohlcv.get("Volume", payload.get("Volume")),
            "look_back_days": payload.get("look_back_days"),
        }
        values = [
            f"{key}={_simple_value(value)}"
            for key, value in preferred_values.items()
            if _is_simple_value(value)
        ]
        if values:
            return "; ".join(values)

    values = []
    for key, value in payload.items():
        if _is_simple_value(value):
            values.append(f"{key}={_simple_value(value)}")
        if len(values) >= 4:
            break
    return "; ".join(values)


def _is_simple_value(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _simple_value(value: Any) -> str:
    text = "null" if value is None else str(value)
    max_length = 120
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def _evidence_links(ledger_items: list[Any]) -> dict[str, tuple[str, str]]:
    links = {}
    for index, item in enumerate(ledger_items, start=1):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id") or "unknown")
        heading_text = f"Evidence {index} {evidence_id}"
        links[evidence_id] = (heading_text, _evidence_anchor(heading_text))
    return links


def _evidence_reference_link(
    evidence_id: str,
    evidence_links: dict[str, tuple[str, str]],
) -> str:
    if evidence_id in evidence_links:
        return _evidence_link(evidence_id, evidence_links[evidence_id][1])
    return _evidence_link(evidence_id, _evidence_anchor(f"Evidence {evidence_id}"))


def _evidence_link(evidence_id: str, anchor: str) -> str:
    return f"[{_markdown_link_label(evidence_id)}](#{anchor})"


def _evidence_anchor(heading_text: str) -> str:
    normalized = []
    for char in heading_text.lower():
        normalized.append(char if char.isalnum() else "-")
    return "".join(normalized).strip("-")


def _markdown_link_label(value: Any) -> str:
    return (
        _markdown_table_cell(value)
        .replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _markdown_table_cell(value: Any) -> str:
    return _markdown_text(value).replace("|", "\\|")


def _markdown_text(value: Any) -> str:
    return " ".join(str(value).splitlines())


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value
