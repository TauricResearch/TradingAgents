from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from tradingagents.agents.utils.rating import parse_rating

from .models import AnalysisRecord


_LABEL_RE = re.compile(r"\*\*(?P<label>[^*]+)\*\*:\s*(?P<value>.+)")
_WHITESPACE_RE = re.compile(r"\s+")
_DISALLOWED_SCRIPT_RE = re.compile(r"[\u0400-\u052F\u0900-\u097F]+")

_MIXED_SCRIPT_REPLACEMENTS = (
    (re.compile(r"фундаментals?", re.IGNORECASE), "펀더멘털"),
    (re.compile(r"фундаментал(?:ы|ов|ом|а|у)?", re.IGNORECASE), "펀더멘털"),
    (re.compile(r"фундамент", re.IGNORECASE), "펀더멘털"),
    (re.compile(r"\bбул\b", re.IGNORECASE), "강세"),
    (re.compile(r"\bбуль\b", re.IGNORECASE), "강세"),
    (re.compile(r"\bबुल\b"), "강세"),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").strip())


def sanitize_generated_text(text: str) -> str:
    sanitized = text or ""
    for pattern, replacement in _MIXED_SCRIPT_REPLACEMENTS:
        sanitized = pattern.sub(replacement, sanitized)
    sanitized = _DISALLOWED_SCRIPT_RE.sub("", sanitized)
    sanitized = re.sub(r" {2,}", " ", sanitized)
    return sanitized.strip()


def extract_markdown_label(text: str, label: str, default: str = "") -> str:
    wanted = label.strip().lower()
    for line in (text or "").splitlines():
        match = _LABEL_RE.match(line.strip())
        if match and match.group("label").strip().lower() == wanted:
            return collapse_whitespace(match.group("value"))
    return default


def make_snippet(text: str, limit: int = 260) -> str:
    compact = collapse_whitespace(text)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _report_lengths(reports: Dict[str, str]) -> Dict[str, int]:
    return {key: len(value or "") for key, value in reports.items()}


def _json_safe(value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, str):
        return sanitize_generated_text(value)
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if hasattr(value, "dict"):
        return _json_safe(value.dict())
    if hasattr(value, "content"):
        return {
            "type": value.__class__.__name__,
            "content": _json_safe(getattr(value, "content", "")),
        }
    return repr(value)


def _make_run_id(ticker: str, trade_date: str, generated_at: str) -> str:
    digest = hashlib.sha1(f"{ticker}|{trade_date}|{generated_at}".encode("utf-8")).hexdigest()[:10]
    return f"{ticker.lower()}-{trade_date}-{digest}"


def _build_reports(final_state: Dict[str, Any]) -> Dict[str, str]:
    return {
        "market_report": sanitize_generated_text(final_state.get("market_report", "")),
        "sentiment_report": sanitize_generated_text(final_state.get("sentiment_report", "")),
        "news_report": sanitize_generated_text(final_state.get("news_report", "")),
        "fundamentals_report": sanitize_generated_text(final_state.get("fundamentals_report", "")),
        "investment_plan": sanitize_generated_text(final_state.get("investment_plan", "")),
        "trader_investment_decision": sanitize_generated_text(
            final_state.get("trader_investment_decision") or final_state.get("trader_investment_plan", "")
        ),
        "final_trade_decision": sanitize_generated_text(final_state.get("final_trade_decision", "")),
        "bull_history": sanitize_generated_text(final_state.get("investment_debate_state", {}).get("bull_history", "")),
        "bear_history": sanitize_generated_text(final_state.get("investment_debate_state", {}).get("bear_history", "")),
        "research_manager_decision": sanitize_generated_text(
            final_state.get("investment_debate_state", {}).get("judge_decision", "")
        ),
        "aggressive_history": sanitize_generated_text(final_state.get("risk_debate_state", {}).get("aggressive_history", "")),
        "conservative_history": sanitize_generated_text(
            final_state.get("risk_debate_state", {}).get("conservative_history", "")
        ),
        "neutral_history": sanitize_generated_text(final_state.get("risk_debate_state", {}).get("neutral_history", "")),
        "portfolio_manager_decision": sanitize_generated_text(
            final_state.get("risk_debate_state", {}).get("judge_decision", "")
        ),
    }


def build_analysis_record(
    final_state: Dict[str, Any],
    *,
    generated_at: Optional[str] = None,
    raw_log_path: Optional[str] = None,
    structured_path: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> AnalysisRecord:
    generated_at = generated_at or utc_now_iso()
    ticker = str(final_state.get("company_of_interest", "")).upper()
    trade_date = str(final_state.get("trade_date", ""))
    reports = _build_reports(final_state)

    final_decision = reports["final_trade_decision"]
    trader_decision = reports["trader_investment_decision"]
    investment_plan = reports["investment_plan"]

    rating = extract_markdown_label(final_decision, "Rating") or parse_rating(final_decision)
    trader_action = extract_markdown_label(trader_decision, "Action") or parse_rating(trader_decision)
    research_recommendation = extract_markdown_label(investment_plan, "Recommendation") or parse_rating(investment_plan)
    decision_summary = extract_markdown_label(final_decision, "Executive Summary") or make_snippet(final_decision)
    investment_thesis = extract_markdown_label(final_decision, "Investment Thesis")
    time_horizon = extract_markdown_label(final_decision, "Time Horizon")
    price_target = safe_float(extract_markdown_label(final_decision, "Price Target"))

    snippets = {
        "market": make_snippet(reports["market_report"]),
        "sentiment": make_snippet(reports["sentiment_report"]),
        "news": make_snippet(reports["news_report"]),
        "fundamentals": make_snippet(reports["fundamentals_report"]),
    }

    run_id = _make_run_id(ticker, trade_date, generated_at)
    record: AnalysisRecord = {
        "run_id": run_id,
        "ticker": ticker,
        "trade_date": trade_date,
        "generated_at": generated_at,
        "rating": rating,
        "trader_action": trader_action,
        "research_recommendation": research_recommendation,
        "decision_summary": decision_summary,
        "investment_thesis": investment_thesis,
        "price_target": price_target,
        "time_horizon": time_horizon,
        "snippets": snippets,
        "reports": reports,
        "report_lengths": _report_lengths(reports),
        "raw_log_path": raw_log_path or "",
        "structured_path": structured_path,
        "metadata": metadata or {},
        "raw_state": _json_safe(final_state),
    }
    return record


def dump_record(record: AnalysisRecord) -> str:
    return json.dumps(record, indent=2, ensure_ascii=False)


def iter_overview_fields(records: Iterable[AnalysisRecord]) -> Iterable[Dict[str, Any]]:
    for record in records:
        yield {
            "run_id": record["run_id"],
            "ticker": record["ticker"],
            "trade_date": record["trade_date"],
            "generated_at": record["generated_at"],
            "rating": record["rating"],
            "trader_action": record["trader_action"],
            "research_recommendation": record["research_recommendation"],
            "decision_summary": record["decision_summary"],
            "structured_path": record["structured_path"],
            "raw_log_path": record["raw_log_path"],
        }


def load_record(path: str | Path) -> AnalysisRecord:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
