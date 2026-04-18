"""Build compact scanner-context packets for Phase 2 analyst prompts.

Extracted from ``langgraph_engine.py`` to isolate text-formatting and
scanner-data assembly from orchestration logic.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
import time
from typing import Any, Dict

from tradingagents.agents.utils.json_utils import extract_json
from tradingagents.agents.utils.scanner_tools import (
    get_bitcoin_price,
    get_cny_usd_rate,
    get_earnings_calendar,
    get_economic_calendar,
    get_eur_usd_rate,
    get_gold_price,
    get_jpy_usd_rate,
    get_oil_prices,
)

logger = logging.getLogger("agent_os.engine")


# ---------------------------------------------------------------------------
# Text formatting helpers
# ---------------------------------------------------------------------------


def clean_line(text: Any, max_chars: int = 0) -> str:
    """Cleans whitespace but no longer truncates characters to prevent LLM hallucinations."""
    line = " ".join(str(text or "").strip().split())
    return line


def dedupe_keep_order(lines: list[str], max_items: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in lines:
        line = clean_line(raw)
        if not line or line in seen:
            continue
        seen.add(line)
        out.append(line)
        if len(out) >= max_items:
            break
    return out


def top_summary_lines(text: Any, max_lines: int = 4) -> list[str]:
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("```"):
            continue
        line = re.sub(r"^[-*0-9).\s]+", "", line).strip()
        cleaned = clean_line(line)
        if cleaned:
            lines.append(cleaned)
    return dedupe_keep_order(lines, max_lines)


def extract_ticker_relevant_lines(
    text: Any,
    ticker: str,
    *,
    sector_tokens: list[str] | None = None,
    max_lines: int = 5,
) -> list[str]:
    raw_lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    ticker_upper = ticker.upper()
    sector_tokens = [tok.lower() for tok in (sector_tokens or []) if tok]

    ticker_hits: list[str] = []
    sector_hits: list[str] = []
    other_hits: list[str] = []
    for raw in raw_lines:
        line = re.sub(r"^[-*0-9).\s]+", "", raw).strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        upper = line.upper()
        lower = line.lower()
        if ticker_upper in upper:
            ticker_hits.append(line)
        elif sector_tokens and any(token in lower for token in sector_tokens):
            sector_hits.append(line)
        else:
            other_hits.append(line)

    prioritized = ticker_hits + sector_hits
    if not prioritized:
        prioritized = other_hits
    return dedupe_keep_order(prioritized, max_lines)


def parse_markdown_rows(raw: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells:
            continue
        if all((not c) or set(c) <= {"-", ":"} for c in cells):
            continue
        rows.append(cells)
    return rows


def drop_table_header(rows: list[list[str]], header_tokens: set[str]) -> list[list[str]]:
    if not rows:
        return rows
    first = {c.lower() for c in rows[0]}
    if first & header_tokens:
        return rows[1:]
    return rows


def format_snapshot_lines(raw: Any, *, max_rows: int = 2) -> list[str]:
    rows = parse_markdown_rows(raw)
    rows = drop_table_header(
        rows,
        header_tokens={"asset", "symbol", "current price", "change", "change %"},
    )
    out: list[str] = []
    for row in rows[:max_rows]:
        if len(row) >= 5:
            out.append(f"{row[0]} {row[2]} ({row[4]})")
        elif len(row) >= 3:
            out.append(f"{row[0]} {row[2]}")
        else:
            out.append(" | ".join(row))
    if out:
        return dedupe_keep_order(out, max_rows)
    fallback = top_summary_lines(raw, max_lines=max_rows)
    return fallback or ["N/A"]


def format_filtered_earnings_rows(
    raw: Any,
    ticker: str,
    peer_tickers: list[str],
    *,
    max_rows: int = 8,
) -> list[str]:
    rows = parse_markdown_rows(raw)
    rows = drop_table_header(
        rows,
        header_tokens={"symbol", "company", "date", "eps estimate", "revenue estimate"},
    )
    ticker_set = {ticker.upper(), *[t.upper() for t in peer_tickers]}

    selected: list[list[str]] = []
    for row in rows:
        joined = " ".join(row).upper()
        if any(t in joined for t in ticker_set):
            selected.append(row)
    if not selected:
        selected = rows[:max_rows]

    formatted: list[str] = []
    for row in selected[:max_rows]:
        symbol = row[0] if len(row) >= 1 else "N/A"
        event_date = row[2] if len(row) >= 3 else "N/A"
        eps = row[3] if len(row) >= 4 else "N/A"
        revenue = row[5] if len(row) >= 6 else (row[-1] if row else "N/A")
        formatted.append(f"{symbol} {event_date} EPS {eps} Rev {revenue}")

    if formatted:
        return dedupe_keep_order(formatted, max_rows)
    fallback = top_summary_lines(raw, max_lines=max_rows)
    return fallback or ["N/A"]


def format_filtered_economic_events(raw: Any, *, max_rows: int = 8) -> list[str]:
    rows = parse_markdown_rows(raw)
    rows = drop_table_header(
        rows,
        header_tokens={"event", "country", "date", "impact", "actual", "forecast"},
    )

    def _priority(row: list[str]) -> int:
        text = " ".join(row).lower()
        high_terms = (
            "high",
            "fomc",
            "cpi",
            "pce",
            "nfp",
            "gdp",
            "unemployment",
            "fed",
            "rate",
        )
        if any(term in text for term in high_terms):
            return 0
        if "medium" in text:
            return 1
        return 2

    if rows:
        ranked = sorted(rows, key=_priority)
        formatted: list[str] = []
        for row in ranked[:max_rows]:
            if len(row) >= 4:
                formatted.append(f"{row[0]} {row[1]} Impact {row[2]} Date {row[3]}")
            elif len(row) >= 2:
                formatted.append(f"{row[0]} {row[1]}")
            else:
                formatted.append(" | ".join(row))
        return dedupe_keep_order(formatted, max_rows)

    fallback = top_summary_lines(raw, max_lines=max_rows)
    return fallback or ["N/A"]


# ---------------------------------------------------------------------------
# Main packet builder
# ---------------------------------------------------------------------------


def build_scanner_context_packet(scan_state: Dict[str, Any], ticker: str) -> str:
    """Build a compact summary-first scanner packet for Phase 2 analyst prompts."""
    ticker = ticker.upper()

    summary_data: Dict[str, Any] = {}
    macro_summary = scan_state.get("macro_scan_summary", "")
    try:
        parsed = extract_json(macro_summary) if isinstance(macro_summary, str) else macro_summary
        if isinstance(parsed, dict):
            summary_data = parsed
    except Exception:
        logger.warning("Failed to parse macro_scan_summary for scanner context packet")

    candidates = summary_data.get("stocks_to_investigate") or summary_data.get("equity_candidates") or []
    ticker_candidate: Dict[str, Any] = {}
    peer_tickers: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        cand_ticker = str(candidate.get("ticker") or candidate.get("symbol") or "").upper()
        if not cand_ticker:
            continue
        if cand_ticker == ticker and not ticker_candidate:
            ticker_candidate = candidate
            continue
        if cand_ticker != ticker and cand_ticker not in peer_tickers:
            peer_tickers.append(cand_ticker)
        if len(peer_tickers) >= 4:
            break

    sector_text = str(ticker_candidate.get("sector") or "")
    sector_tokens = [
        tok.strip().lower()
        for tok in re.split(r"[/,|&\\-]+", sector_text)
        if tok and tok.strip()
    ]
    primary_sector = clean_line(sector_text, max_chars=60) or "Unknown"

    rationale = clean_line(
        ticker_candidate.get("rationale") or "No ticker-specific rationale in macro summary."
    )
    thesis_angle = clean_line(ticker_candidate.get("thesis_angle") or "N/A")
    conviction = clean_line(ticker_candidate.get("conviction") or "N/A", max_chars=40)
    catalysts = ticker_candidate.get("key_catalysts") or []
    if isinstance(catalysts, list):
        catalyst_line = "; ".join(clean_line(item, 120) for item in catalysts if str(item).strip())
    else:
        catalyst_line = clean_line(catalysts, 240)
    catalyst_line = catalyst_line or "N/A"

    candidate_risks = ticker_candidate.get("risks") or []
    if isinstance(candidate_risks, list):
        candidate_risk_line = "; ".join(
            clean_line(item, 120) for item in candidate_risks if str(item).strip()
        )
    else:
        candidate_risk_line = clean_line(candidate_risks, 240)
    candidate_risk_line = candidate_risk_line or "N/A"

    theme_lines: list[str] = []
    for item in summary_data.get("key_themes") or []:
        if isinstance(item, dict):
            theme = clean_line(item.get("theme"), 80)
            desc = clean_line(item.get("description"), 140)
            conviction_label = clean_line(item.get("conviction"), 20)
            line = f"{theme}: {desc}" if theme else desc
            if conviction_label:
                line = f"{line} (conviction={conviction_label})"
            if line.strip():
                theme_lines.append(line)
        else:
            theme_lines.append(clean_line(item, 200))
    theme_lines = dedupe_keep_order(theme_lines, 2) or ["N/A"]

    macro_risk_lines = [
        clean_line(item, 180)
        for item in (summary_data.get("risk_factors") or [])
        if str(item).strip()
    ]
    macro_risk_lines = dedupe_keep_order(macro_risk_lines, 3)
    if not macro_risk_lines:
        macro_risk_lines = [candidate_risk_line]

    # Scanner summaries (summary-first)
    smart_money_summary = scan_state.get("smart_money_summary", "")
    factor_summary = scan_state.get("factor_alignment_summary", "")
    drift_summary = scan_state.get("drift_opportunities_summary", "")
    sector_summary = scan_state.get("sector_summary", "")
    geopolitical_summary = scan_state.get("geopolitical_summary", "")
    market_movers_summary = scan_state.get("market_movers_summary", "")
    industry_summary = scan_state.get("industry_deep_dive_summary", "")

    smart_lines = extract_ticker_relevant_lines(
        smart_money_summary, ticker, sector_tokens=sector_tokens, max_lines=5,
    ) or ["N/A"]
    factor_lines = extract_ticker_relevant_lines(
        factor_summary, ticker, sector_tokens=sector_tokens, max_lines=5,
    ) or ["N/A"]
    drift_lines = extract_ticker_relevant_lines(
        drift_summary, ticker, sector_tokens=sector_tokens, max_lines=5,
    ) or ["N/A"]
    sector_lines = extract_ticker_relevant_lines(
        sector_summary, ticker, sector_tokens=sector_tokens, max_lines=3,
    ) or ["N/A"]
    market_pulse_lines = top_summary_lines(market_movers_summary, max_lines=2) or ["N/A"]
    geo_pulse_lines = top_summary_lines(geopolitical_summary, max_lines=2) or ["N/A"]
    industry_pulse_lines = top_summary_lines(industry_summary, max_lines=2) or ["N/A"]

    # Ground-truth blocks
    gold_snapshot = _fetch_ground_truth(get_gold_price, "gold price", max_rows=1)
    oil_snapshot = _fetch_ground_truth(get_oil_prices, "oil prices", max_rows=2)
    btc_snapshot = _fetch_ground_truth(get_bitcoin_price, "bitcoin price", max_rows=1)
    eur_snapshot = _fetch_ground_truth(get_eur_usd_rate, "EUR/USD rate", max_rows=1)
    jpy_snapshot = _fetch_ground_truth(get_jpy_usd_rate, "JPY/USD rate", max_rows=1)
    cny_snapshot = _fetch_ground_truth(get_cny_usd_rate, "CNY/USD rate", max_rows=1)

    earnings_rows: list[str] = ["N/A"]
    economic_rows: list[str] = ["N/A"]

    scan_date_str = scan_state.get("scan_date", time.strftime("%Y-%m-%d"))
    try:
        scan_dt = _dt.datetime.strptime(scan_date_str, "%Y-%m-%d")
        from_date = (scan_dt - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
        to_date = (scan_dt + _dt.timedelta(days=14)).strftime("%Y-%m-%d")

        try:
            earnings_rows = format_filtered_earnings_rows(
                get_earnings_calendar.invoke({"from_date": from_date, "to_date": to_date}),
                ticker,
                peer_tickers,
                max_rows=8,
            )
        except Exception as e:
            logger.warning("Failed to fetch earnings calendar for scanner context: %s", e)
        try:
            economic_rows = format_filtered_economic_events(
                get_economic_calendar.invoke({"from_date": from_date, "to_date": to_date}),
                max_rows=8,
            )
        except Exception as e:
            logger.warning("Failed to fetch economic calendar for scanner context: %s", e)
    except Exception as e:
        logger.warning("Failed to parse scan date for calendar data: %s", e)

    def _bullet_lines(items: list[str]) -> str:
        return "\n".join(f"- {line}" for line in items)

    commodity_block = _bullet_lines(gold_snapshot + oil_snapshot + btc_snapshot)
    fx_block = _bullet_lines(eur_snapshot + jpy_snapshot + cny_snapshot)
    earnings_block = _bullet_lines(earnings_rows)
    economic_block = _bullet_lines(economic_rows)
    smart_block = _bullet_lines(smart_lines)
    factor_block = _bullet_lines(factor_lines)
    drift_block = _bullet_lines(drift_lines)
    sector_block = _bullet_lines(sector_lines)
    spillover_block = _bullet_lines(market_pulse_lines[:1])
    themes_block = _bullet_lines(theme_lines)
    geo_block = _bullet_lines(geo_pulse_lines)
    movers_block = _bullet_lines(market_pulse_lines)
    industry_block = _bullet_lines(industry_pulse_lines)
    risk_block = _bullet_lines(macro_risk_lines)

    packet = f"""# SCANNER CONTEXT PACKET: {ticker}
Date: {scan_state.get('scan_date', 'N/A')}

## 1) Selection Context
- Ticker: {ticker}
- Rationale: {rationale}
- Conviction: {conviction}
- Thesis Angle: {thesis_angle}
- Catalysts: {catalyst_line}
- Risks: {candidate_risk_line}

## 2) Ground Truth
### Commodity Snapshot
{commodity_block}

### FX Snapshot
{fx_block}

### Filtered Earnings Rows
{earnings_block}

### Filtered Economic Events
{economic_block}

## 3) Ticker-Relevant Scanner Signals
### Smart Money
{smart_block}

### Factor Alignment
{factor_block}

### Drift
{drift_block}

## 4) Sector Context
- Primary Sector: {primary_sector}
- Sector Summary:
{sector_block}
- Related Spillover:
{spillover_block}

## 5) Macro Themes
{themes_block}
- Geopolitical Pulse:
{geo_block}
- Market Movers Pulse:
{movers_block}
- Industry Deep Dive Pulse:
{industry_block}

## 6) Risk Factors
{risk_block}
"""
    return packet


def _fetch_ground_truth(tool_fn: Any, label: str, *, max_rows: int = 1) -> list[str]:
    """Invoke a scanner tool and format the result, returning ["N/A"] on failure."""
    try:
        return format_snapshot_lines(tool_fn.invoke({}), max_rows=max_rows)
    except Exception as e:
        logger.warning("Failed to fetch %s for scanner context: %s", label, e)
        return ["N/A"]
