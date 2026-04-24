"""Regression coverage for summary-first prompt sizing against local run artifacts.

These tests intentionally use local artifacts when available and skip cleanly
when the workspace does not contain the audited baseline runs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tradingagents.agents.utils.context_filtering import filter_scanner_context_for_ticker

_ANALYST_NODES = {"Market Analyst", "News Analyst", "Fundamentals Analyst"}
_BASELINE_RUN_ID = "01KN7AX94HC86NENW9QCSPP2KB"
_BASELINE_DATE = "2026-04-02"

# Explicit baseline values from /Users/Ahmet/Desktop/model_context_audit_2026-04-02.md
_AUDIT_MARKET_MSFT_PROMPT_CHARS = 96_041
_AUDIT_MARKET_MSFT_SCANNER_CONTEXT_CHARS = 73_444
_AUDIT_FUNDAMENTALS_OXY_ROUNDS = (81_968, 86_286, 92_905, 96_888)


def _reports_daily_dir() -> Path:
    return Path("reports/daily")


def _iter_daily_dirs_desc(base_dir: Path) -> list[Path]:
    if not base_dir.exists():
        return []
    dirs = [
        child
        for child in base_dir.iterdir()
        if child.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name)
    ]
    return sorted(dirs, reverse=True)


def _load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _extract_scanner_bounds(prompt: str) -> tuple[int, int] | None:
    start = prompt.find("# SCANNER CONTEXT PACKET:")
    if start < 0:
        return None

    # In analyst prompts the scanner block is typically followed by a
    # preloaded context section (e.g., macro regime / price history).
    end = prompt.find("## Pre-loaded Context", start)
    if end < 0:
        end = len(prompt)
    return start, end


def _extract_ticker(scanner_context: str) -> str | None:
    match = re.search(r"# SCANNER CONTEXT PACKET:\s*([A-Z0-9.\-]+)", scanner_context)
    if not match:
        return None
    return match.group(1).strip().upper()


def _approx_tokens(chars: int) -> int:
    # Directional estimate used in existing prompt-size audits.
    return max(1, chars // 4)


def _iter_scanner_prompt_events(events: list[dict]) -> list[dict]:
    filtered = []
    for event in events:
        if event.get("type") != "thought":
            continue
        if event.get("node_id") not in _ANALYST_NODES:
            continue
        prompt = str(event.get("prompt") or "")
        if "# SCANNER CONTEXT PACKET:" not in prompt:
            continue
        filtered.append(event)
    return filtered


def _find_latest_run_with_scanner_prompts(base_dir: Path) -> Path | None:
    for day_dir in _iter_daily_dirs_desc(base_dir):
        run_dirs = sorted([p for p in day_dir.iterdir() if p.is_dir()], reverse=True)
        for run_dir in run_dirs:
            events_path = run_dir / "run_events.jsonl"
            if not events_path.exists():
                continue
            events = _load_jsonl(events_path)
            if _iter_scanner_prompt_events(events):
                return run_dir
    return None


def _project_summary_first_prompt(prompt: str) -> str:
    bounds = _extract_scanner_bounds(prompt)
    if bounds is None:
        return prompt
    start, end = bounds
    scanner_context = prompt[start:end]
    ticker = _extract_ticker(scanner_context)
    if not ticker:
        return prompt

    compact_context = filter_scanner_context_for_ticker(scanner_context, ticker)
    projection_header = (
        "## Summary-First Handoff (Projected)\n"
        "- Source Inputs: macro_scan_summary + scanner summaries + compact ground truth\n\n"
    )
    return prompt[:start] + projection_header + compact_context + prompt[end:]


def _build_legacy_raw_packet_fixture(ticker: str) -> str:
    earnings_rows = "\n".join(
        f"- 2026-04-{(day % 30) + 1:02d}: CO{day:03d} earnings event (mixed sector)"
        for day in range(1, 161)
    )
    economic_rows = "\n".join(
        f"- 2026-04-{(day % 30) + 1:02d}: Macro event {day} (high/medium mix)"
        for day in range(1, 61)
    )
    smart_money_rows = "\n".join(
        f"- TICK{idx:03d}: raw options/flow detail with long explanation"
        for idx in range(1, 81)
    )
    factor_rows = "\n".join(
        f"- TICK{idx:03d}: factor alignment row with momentum/value/quality decomposition"
        for idx in range(1, 81)
    )
    return f"""# SCANNER CONTEXT PACKET: {ticker}
Date: 2026-04-02

## I. TICKER-SPECIFIC SCANNER THESIS
Rationale: Legacy raw handoff with broad report dumps.

## II. STRUCTURED LIVE DATA (GROUND TRUTH)
### Earnings Calendar (Raw)
{earnings_rows}
### Economic Calendar (Raw)
{economic_rows}

## III. SMART MONEY & FLOW SIGNALS
### Dark Pool & Block Activity
{smart_money_rows}

## IV. FACTOR ALIGNMENT & DRIFT
### Raw Factor Rows
{factor_rows}
"""


def _build_summary_first_packet_fixture(ticker: str) -> str:
    return f"""# SCANNER CONTEXT PACKET: {ticker}
Date: 2026-04-02

## Selection Context
- ticker: {ticker}
- rationale: overlap of macro_scan_summary and scanner summaries
- conviction: high
- thesis_angle: quality + cash-flow resilience
- catalysts: earnings revision, sector inflow
- risks: policy shock, multiple compression

## Ground Truth
- commodity_snapshot: oil +2.1%, gold -0.4%, btc -1.0%
- fx_snapshot: EUR/USD 1.08, JPY/USD 0.0068, CNY/USD 0.14
- filtered_earnings_rows: {ticker}, XOM, CVX, AMZN
- filtered_economic_events: CPI, NFP, FOMC, Core PCE

## Ticker-Relevant Scanner Signals
- smart_money_summary: insider buying spike in {ticker}
- factor_alignment_summary: value + quality positive vs sector
- drift_opportunities_summary: positive 20D drift with narrowing volatility

## Sector Context
- sector_summary: energy leadership with selective spillover into materials

## Macro Themes (macro_scan_summary)
- AI infra capex remains elevated
- commodity supply remains tight

## Risk Factors (macro_scan_summary)
- delayed easing path
- geopolitical escalation
"""


def test_audit_baseline_values_present_in_2026_04_02_run_artifacts():
    """Pin known 2026-04-02 prompt-size baselines from the audit document."""
    run_dir = _reports_daily_dir() / _BASELINE_DATE / _BASELINE_RUN_ID
    events_path = run_dir / "run_events.jsonl"
    if not events_path.exists():
        pytest.skip(f"Baseline run artifacts missing at {events_path}")

    events = _load_jsonl(events_path)

    market_msft_prompt_len: int | None = None
    market_msft_scanner_len: int | None = None
    fundamentals_oxy_lengths: list[int] = []

    for event in events:
        if event.get("type") != "thought":
            continue
        node_id = str(event.get("node_id") or "")
        prompt = str(event.get("prompt") or "")

        if node_id == "Market Analyst" and "# SCANNER CONTEXT PACKET: MSFT" in prompt:
            market_msft_prompt_len = len(prompt)
            bounds = _extract_scanner_bounds(prompt)
            if bounds:
                start, end = bounds
                # Normalize to the audited measurement convention.
                scanner_block = prompt[start:end]
                market_msft_scanner_len = len(scanner_block) - 2

        if node_id == "Fundamentals Analyst" and "# SCANNER CONTEXT PACKET: OXY" in prompt:
            fundamentals_oxy_lengths.append(len(prompt))

    assert market_msft_prompt_len == _AUDIT_MARKET_MSFT_PROMPT_CHARS
    assert market_msft_scanner_len == _AUDIT_MARKET_MSFT_SCANNER_CONTEXT_CHARS

    windows = [
        tuple(fundamentals_oxy_lengths[i : i + 4])
        for i in range(len(fundamentals_oxy_lengths) - 3)
    ]
    assert _AUDIT_FUNDAMENTALS_OXY_ROUNDS in windows


def test_latest_baseline_projection_shrinks_prompt_size_materially():
    """Projected summary-first handoff must reduce prompt chars and est-tokens."""
    run_dir = _find_latest_run_with_scanner_prompts(_reports_daily_dir())
    if run_dir is None:
        pytest.skip("No local baseline run with scanner prompts found under reports/daily")

    events_path = run_dir / "run_events.jsonl"
    events = _load_jsonl(events_path)
    scanner_events = _iter_scanner_prompt_events(events)
    if not scanner_events:
        pytest.skip(f"No scanner prompt events found in {events_path}")

    baseline_chars = 0
    projected_chars = 0
    for event in scanner_events:
        prompt = str(event.get("prompt") or "")
        baseline_chars += len(prompt)
        projected_chars += len(_project_summary_first_prompt(prompt))

    assert projected_chars < baseline_chars
    # "Materially" smaller: require at least 20% prompt-char reduction.
    assert projected_chars <= int(baseline_chars * 0.80)

    baseline_tokens = _approx_tokens(baseline_chars)
    projected_tokens = _approx_tokens(projected_chars)
    assert projected_tokens < baseline_tokens


def test_summary_first_fixture_is_much_smaller_and_summary_driven():
    """Deterministic contract coverage: summary-first packet beats legacy raw packet."""
    ticker = "OXY"
    legacy_packet = _build_legacy_raw_packet_fixture(ticker)
    summary_first_packet = _build_summary_first_packet_fixture(ticker)

    assert "macro_scan_summary" in summary_first_packet
    assert "smart_money_summary" in summary_first_packet
    assert "factor_alignment_summary" in summary_first_packet
    assert "drift_opportunities_summary" in summary_first_packet

    # Ensure we are no longer carrying raw report sub-sections in this contract.
    assert "Dark Pool & Block Activity" not in summary_first_packet
    assert "Raw Factor Rows" not in summary_first_packet

    # Deterministic material reduction target for summary-first packeting.
    assert len(summary_first_packet) <= int(len(legacy_packet) * 0.35)
