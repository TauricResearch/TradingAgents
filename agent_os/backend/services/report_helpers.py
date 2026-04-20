"""Report and artifact persistence helpers for LangGraphEngine.

Extracted from ``langgraph_engine.py`` to keep report-writing and
scan-data normalization separate from orchestration logic.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

from tradingagents.instruments import (
    CanonicalInstrument,
    is_equity_pipeline_supported,
    resolve_instrument,
)

logger = logging.getLogger("agent_os.engine")


_PROMPT_LEAK_PREFIXES = (
    "we need to ",
    "we need to analyze",
    "we need to follow instruction",
    "we have limited data",
    "we can use ",
    "we cannot ",
    "we should ",
    "we must ",
    "let's ",
    "now we need to ",
    "must use only ",
    "you are a helpful ai assistant",
    "you are a researcher tasked",
    "strict constraints:",
    "## normal operation",
    "for your reference",
    "use the provided tools",
    "## your task",
    "## critical abort trigger",
    "## pre-loaded foundational data",
    "## pre-loaded context",
    "## scanner context",
    "0. strict ground truth",
)

_PROMPT_LEAK_SUBSTRINGS = (
    "could format as",
    "we can create",
    "we'll just use",
    "now produce final answer",
    "let's extract numbers",
    "the packet includes:",
    "we need to produce",
    "we need to decide",
    "we need to cite",
    "we might have to state",
    "likely each bullet is",
    "we cannot invent",
    "we cannot give entry price",
    "let's craft",
)

_DECISION_SECTION_HEADINGS = (
    "Strongest Bull Evidence:",
    "Strongest Bear Evidence:",
    "Recommendation:",
    "Rationale:",
    "Strategic Actions:",
    "Research Manager's Verdict:",
    "Entry Setup:",
    "Risk Parameters:",
    "Catalyst Timeline:",
    "FINAL TRANSACTION PROPOSAL:",
)


def sanitize_for_json(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable objects to plain types.

    LangGraph final states may contain LangChain message objects
    (HumanMessage, AIMessage, etc.) in the ``messages`` field, as well as
    other non-serializable objects from third-party libraries.  All such
    objects are converted to strings as a last resort so ``json.dumps``
    never raises ``TypeError``.
    """
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    if hasattr(obj, "content") and hasattr(obj, "type"):
        res = {
            "type": str(getattr(obj, "type", "unknown")),
            "content": str(getattr(obj, "content", "")),
        }
        # Preserve critical fields for LangGraph/LangChain reconstruction
        if hasattr(obj, "id") and obj.id is not None:
            res["id"] = str(obj.id)
        if hasattr(obj, "tool_call_id") and obj.tool_call_id is not None:
            res["tool_call_id"] = str(obj.tool_call_id)
        if hasattr(obj, "name") and obj.name is not None:
            res["name"] = str(obj.name)
        if hasattr(obj, "tool_calls") and obj.tool_calls:
            res["tool_calls"] = sanitize_for_json(obj.tool_calls)
        if hasattr(obj, "additional_kwargs") and obj.additional_kwargs:
            res["additional_kwargs"] = sanitize_for_json(obj.additional_kwargs)
        return res
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


def _looks_like_prompt_leak(line: str) -> bool:
    normalized = " ".join(str(line or "").strip().split()).lower()
    if not normalized:
        return False
    if normalized.startswith(("strongest bull evidence:", "strongest bear evidence:", "recommendation:", "rationale:", "strategic actions:")):
        return True
    if "final transaction proposal:" in normalized and normalized.startswith("if you or any other assistant"):
        return True
    return any(
        normalized.startswith(prefix)
        for prefix in _PROMPT_LEAK_PREFIXES
    ) or any(fragment in normalized for fragment in _PROMPT_LEAK_SUBSTRINGS)


def sanitize_report_text_for_persistence(text: Any) -> str:
    """Drop obvious prompt/instruction leakage before persisting reports."""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in raw.split("\n"):
        if _looks_like_prompt_leak(line):
            continue
        lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_decision_bullets(text: Any) -> str:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    headings_seen = False
    bullets: list[str] = []

    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(heading) for heading in _DECISION_SECTION_HEADINGS):
            headings_seen = True
            continue
        if _looks_like_prompt_leak(stripped):
            continue
        if headings_seen:
            if stripped.startswith(("- ", "* ")):
                bullets.append("- " + stripped[2:].strip())
                continue
            if bullets and line[:1].isspace():
                bullets[-1] = f"{bullets[-1]} {stripped}"

    if bullets:
        return "\n".join(bullets).strip()

    fallback = sanitize_report_text_for_persistence(raw)
    fallback_lines = []
    for line in fallback.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("- ", "* ")):
            fallback_lines.append("- " + stripped[2:].strip())
    return "\n".join(fallback_lines).strip() or fallback


def _render_market_report_json(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw.startswith("{"):
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""

    lines: list[str] = []
    timeframe = str(payload.get("timeframe") or "").strip()
    executive_summary = str(payload.get("executive_summary") or "").strip()
    if timeframe:
        lines.append(f"- Timeframe: {timeframe}")
    if executive_summary:
        lines.append(f"- Executive Summary: {executive_summary}")

    for theme in (payload.get("key_themes") or [])[:3]:
        if not isinstance(theme, dict):
            continue
        theme_name = str(theme.get("theme") or "").strip()
        description = str(theme.get("description") or "").strip()
        conviction = str(theme.get("conviction") or "").strip()
        timeframe_value = str(theme.get("timeframe") or "").strip()
        if not any((theme_name, description, conviction, timeframe_value)):
            continue
        detail = "; ".join(
            part
            for part in (
                description,
                f"conviction={conviction}" if conviction else "",
                f"timeframe={timeframe_value}" if timeframe_value else "",
            )
            if part
        )
        lines.append(f"- Theme: {theme_name}" + (f" | {detail}" if detail else ""))

    for stock in (payload.get("stocks_to_investigate") or [])[:3]:
        if not isinstance(stock, dict):
            continue
        ticker = str(stock.get("ticker") or "").strip()
        rationale = str(stock.get("rationale") or "").strip()
        conviction = str(stock.get("conviction") or "").strip()
        catalyst_count = len(stock.get("key_catalysts") or [])
        risk_count = len(stock.get("risks") or [])
        if not ticker:
            continue
        suffix = "; ".join(
            part
            for part in (
                rationale,
                f"conviction={conviction}" if conviction else "",
                f"catalysts={catalyst_count}" if catalyst_count else "",
                f"risks={risk_count}" if risk_count else "",
            )
            if part
        )
        lines.append(f"- Candidate: {ticker}" + (f" | {suffix}" if suffix else ""))

    return "\n".join(lines).strip()


def format_report_section_for_persistence(section_key: str, text: Any) -> str:
    if section_key in {"investment_plan", "trader_investment_plan", "final_trade_decision"}:
        return _extract_decision_bullets(text)
    if section_key == "market_report":
        rendered_market = _render_market_report_json(text)
        if rendered_market:
            return rendered_market
    return sanitize_report_text_for_persistence(text)


def write_complete_report_md(
    final_state: Dict[str, Any], ticker: str, save_dir: Path
) -> None:
    """Write a human-readable complete_report.md from the pipeline final state."""
    sections = []
    header = (
        f"# Trading Analysis Report: {ticker}\n\n"
        f"Generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )

    analyst_parts = []
    for key, label in (
        ("market_report", "Market Analyst"),
        ("sentiment_report", "Social Analyst"),
        ("news_report", "News Analyst"),
        ("fundamentals_report", "Fundamentals Analyst"),
    ):
        cleaned = format_report_section_for_persistence(key, final_state.get(key))
        if cleaned:
            analyst_parts.append(f"### {label}\n{cleaned}")
    if analyst_parts:
        sections.append("## I. Analyst Team Reports\n\n" + "\n\n".join(analyst_parts))

    investment_plan = format_report_section_for_persistence("investment_plan", final_state.get("investment_plan"))
    if investment_plan:
        sections.append(f"## II. Research Team Decision\n\n{investment_plan}")

    trader_plan = format_report_section_for_persistence("trader_investment_plan", final_state.get("trader_investment_plan"))
    if trader_plan:
        sections.append(f"## III. Trading Team Plan\n\n{trader_plan}")

    final_decision = format_report_section_for_persistence("final_trade_decision", final_state.get("final_trade_decision"))
    if final_decision:
        sections.append(f"## IV. Final Decision\n\n{final_decision}")

    (save_dir / "complete_report.md").write_text(header + "\n\n".join(sections))


def extract_tickers_from_scan_data(scan_data: Dict[str, Any] | None) -> list[str]:
    """Extract ticker symbols from a ReportStore scan summary dict.

    Handles two shapes from the macro synthesis LLM output:
    * List of dicts: ``[{'ticker': 'AAPL', ...}, ...]``
    * List of strings: ``['AAPL', 'TSLA', ...]``

    Also checks both ``stocks_to_investigate`` and ``watchlist`` keys.
    Returns a deduplicated list of common-stock symbols in original order.
    """
    if not scan_data:
        return []
    raw_stocks = scan_data.get("equity_candidates") or scan_data.get("stocks_to_investigate") or scan_data.get("watchlist") or []
    seen: set[str] = set()
    tickers: list[str] = []
    for item in raw_stocks:
        if isinstance(item, dict):
            sym = item.get("ticker") or item.get("symbol") or ""
        elif isinstance(item, str):
            sym = item
        else:
            continue
        instrument = resolve_instrument(sym, source_context="scan")
        if not is_equity_pipeline_supported(instrument):
            continue
        if instrument.canonical_symbol and instrument.canonical_symbol not in seen:
            seen.add(instrument.canonical_symbol)
            tickers.append(instrument.canonical_symbol)
    return tickers


def extract_pipeline_instruments_from_scan_data(
    scan_data: Dict[str, Any] | None,
) -> list[CanonicalInstrument]:
    """Extract resolved instruments from scan data for pipeline queuing."""
    if not scan_data:
        return []
    raw_stocks = scan_data.get("equity_candidates") or scan_data.get("stocks_to_investigate") or scan_data.get("watchlist") or []
    seen: set[str] = set()
    instruments: list[CanonicalInstrument] = []
    for item in raw_stocks:
        if isinstance(item, dict):
            sym = item.get("ticker") or item.get("symbol") or ""
        elif isinstance(item, str):
            sym = item
        else:
            continue
        instrument = resolve_instrument(sym, source_context="scan")
        if not is_equity_pipeline_supported(instrument):
            continue
        if instrument.instrument_key in seen:
            continue
        seen.add(instrument.instrument_key)
        instruments.append(instrument)
    return instruments


def normalize_scan_summary(scan_data: Dict[str, Any] | None) -> Dict[str, Any]:
    """Normalize raw scan summary data, classifying candidates by asset type."""
    if not isinstance(scan_data, dict):
        return {}
    normalized = dict(scan_data)
    raw_stocks = normalized.get("stocks_to_investigate") or normalized.get("watchlist")
    if raw_stocks is None:
        raw_stocks = normalized.get("equity_candidates") or []
    equity_candidates: list[dict[str, Any]] = []
    tracked_market_instruments: list[dict[str, Any]] = []
    tracked_crypto_instruments: list[dict[str, Any]] = []
    for item in raw_stocks:
        if isinstance(item, dict):
            candidate = dict(item)
            sym = candidate.get("ticker") or candidate.get("symbol") or ""
        elif isinstance(item, str):
            sym = item
            candidate = {"ticker": str(item).strip().upper()}
        else:
            continue
        instrument = resolve_instrument(sym, source_context="scan")
        candidate.update(instrument.to_metadata())
        candidate["ticker"] = instrument.canonical_symbol
        if is_equity_pipeline_supported(instrument):
            equity_candidates.append(candidate)
        elif instrument.asset_class in {"etf", "index"}:
            tracked_market_instruments.append(candidate)
        elif instrument.asset_class == "crypto":
            tracked_crypto_instruments.append(candidate)
    normalized["equity_candidates"] = equity_candidates
    normalized["tracked_market_instruments"] = tracked_market_instruments
    normalized["tracked_crypto_instruments"] = tracked_crypto_instruments
    return normalized
