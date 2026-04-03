"""Report and artifact persistence helpers for LangGraphEngine.

Extracted from ``langgraph_engine.py`` to keep report-writing and
scan-data normalization separate from orchestration logic.
"""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any, Dict

from tradingagents.instruments import (
    CanonicalInstrument,
    is_equity_pipeline_supported,
    resolve_instrument,
)

logger = logging.getLogger("agent_os.engine")


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
        return {
            "type": str(getattr(obj, "type", "unknown")),
            "content": str(getattr(obj, "content", "")),
        }
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


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
        if final_state.get(key):
            analyst_parts.append(f"### {label}\n{final_state[key]}")
    if analyst_parts:
        sections.append("## I. Analyst Team Reports\n\n" + "\n\n".join(analyst_parts))

    if final_state.get("investment_plan"):
        sections.append(f"## II. Research Team Decision\n\n{final_state['investment_plan']}")

    if final_state.get("trader_investment_plan"):
        sections.append(f"## III. Trading Team Plan\n\n{final_state['trader_investment_plan']}")

    if final_state.get("final_trade_decision"):
        sections.append(f"## IV. Final Decision\n\n{final_state['final_trade_decision']}")

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
