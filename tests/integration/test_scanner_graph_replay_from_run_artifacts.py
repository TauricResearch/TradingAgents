"""Replay scanner graph wiring from prior run artifacts.

This test uses raw scanner reports and tool call logs from a previous local run
without calling live vendor tools. It guards the deterministic graph contract:
scanner evidence must travel through ScannerState into summarizers and macro
synthesis, rather than being recovered from latest-run or wall-clock fallbacks.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.scanners.macro_synthesis import create_macro_synthesis
from tradingagents.agents.scanners.scanner_summarizer import create_scanner_summarizer
from tradingagents.graph.scanner_setup import ScannerGraphSetup

RUN_DATE = "2026-04-24"
SOURCE_RUN_ID = "01KPZYDEPYJ10ZFJFGQ5YT1Z91"
REPLAY_RUN_ID = "REPLAY_GRAPH_STATE_FROM_ARTIFACTS"

REPORT_FIELDS = {
    "gatekeeper_scanner": "gatekeeper_universe_report",
    "geopolitical_scanner": "geopolitical_report",
    "market_movers_scanner": "market_movers_report",
    "sector_scanner": "sector_performance_report",
    "factor_alignment_scanner": "factor_alignment_report",
    "drift_scanner": "drift_opportunities_report",
    "smart_money_scanner": "smart_money_report",
    "industry_deep_dive": "industry_deep_dive_report",
}

SUMMARY_NODES = {
    "summarize_gatekeeper": ("gatekeeper_universe_report", "gatekeeper_summary"),
    "summarize_geopolitical": ("geopolitical_report", "geopolitical_summary"),
    "summarize_market_movers": ("market_movers_report", "market_movers_summary"),
    "summarize_sector": ("sector_performance_report", "sector_summary"),
    "summarize_factor_alignment": ("factor_alignment_report", "factor_alignment_summary"),
    "summarize_drift": ("drift_opportunities_report", "drift_opportunities_summary"),
    "summarize_smart_money": ("smart_money_report", "smart_money_summary"),
    "summarize_industry_deep_dive": ("industry_deep_dive_report", "industry_deep_dive_summary"),
}

EXPECTED_TOOLS = {
    "get_gatekeeper_universe",
    "get_topic_news",
    "get_todays_sovereign_cds",
    "get_gold_price",
    "get_oil_prices",
    "get_bitcoin_price",
    "get_eur_usd_rate",
    "get_jpy_usd_rate",
    "get_cny_usd_rate",
    "get_market_indices",
    "get_sector_performance",
    "get_earnings_calendar",
    "get_gap_candidates",
    "get_insider_buying_stocks",
    "get_unusual_volume_stocks",
    "get_breakout_accumulation_stocks",
    "get_industry_performance",
}


def _artifact_market_dir() -> Path:
    return Path("reports") / "daily" / RUN_DATE / SOURCE_RUN_ID / "market"


def _load_reports(market_dir: Path) -> dict[str, str]:
    reports = {}
    for field in REPORT_FIELDS.values():
        path = market_dir / f"{field}.md"
        if not path.exists():
            pytest.skip(f"Missing scanner replay artifact: {path}")
        reports[field] = path.read_text(encoding="utf-8")
    return reports


def _load_tool_names(market_dir: Path) -> set[str]:
    log_path = market_dir / "run_log.jsonl"
    if not log_path.exists():
        pytest.skip(f"Missing scanner replay artifact: {log_path}")

    tool_names: set[str] = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("kind") == "tool" and event.get("success") is True:
            tool_names.add(str(event.get("tool")))
    return tool_names


def _load_llm_prompts(market_dir: Path) -> list[str]:
    log_path = market_dir / "run_log.jsonl"
    if not log_path.exists():
        pytest.skip(f"Missing scanner replay artifact: {log_path}")

    prompts: list[str] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("kind") == "llm" and event.get("prompt"):
            prompts.append(str(event["prompt"]))
    return prompts


def test_scanner_graph_replays_prior_reports_and_tool_inputs_without_fallback(monkeypatch):
    market_dir = _artifact_market_dir()
    reports = _load_reports(market_dir)
    tool_names = _load_tool_names(market_dir)
    llm_prompts = _load_llm_prompts(market_dir)
    missing_tools = EXPECTED_TOOLS - tool_names
    assert not missing_tools, (
        f"Prior run did not record expected tool inputs: {sorted(missing_tools)}"
    )
    assert llm_prompts, "Prior run did not record scanner LLM prompts."
    assert all(f"current date is {RUN_DATE}" in prompt for prompt in llm_prompts), (
        "Prior scanner prompts did not consistently receive the propagated scan date."
    )

    summary_sources_seen: list[str] = []

    class SummaryLLM:
        def invoke(self, prompt: str):
            assert "Scanner source:" in prompt
            source_line = next(
                line for line in prompt.splitlines() if line.startswith("Scanner source:")
            )
            summary_sources_seen.append(source_line)
            return SimpleNamespace(content=f"- replay | {source_line} | evidence propagated")

    macro_prompts: list[str] = []

    def _macro_llm(prompt_value):
        prompt_text = prompt_value.to_string()
        macro_prompts.append(prompt_text)
        assert "0 of 7 upstream sources provided usable evidence" not in prompt_text
        assert "replay | Scanner source:" in prompt_text
        return AIMessage(
            content=(
                '{"timeframe":"1 month","executive_summary":"Replay synthesis",'
                '"macro_context":{},"key_themes":[],"stocks_to_investigate":[],'
                '"risk_factors":[]}'
            )
        )

    monkeypatch.setattr(
        "tradingagents.agents.scanners.scanner_summarizer.save_node_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.save_node_report",
        lambda *_args, **_kwargs: None,
    )

    def make_replay_node(node_name: str, field: str):
        def _node(state):
            assert state["scan_date"] == RUN_DATE
            assert state["run_id"] == REPLAY_RUN_ID
            return {field: reports[field], "sender": node_name}

        return _node

    agents = {
        node_name: make_replay_node(node_name, field) for node_name, field in REPORT_FIELDS.items()
    }
    for node_name, (report_key, summary_key) in SUMMARY_NODES.items():
        agents[node_name] = create_scanner_summarizer(SummaryLLM(), report_key, summary_key)
    agents["macro_synthesis"] = create_macro_synthesis(
        RunnableLambda(_macro_llm),
        max_scan_tickers=3,
        scan_horizon_days=30,
    )

    initial_state = {
        "scan_date": RUN_DATE,
        "run_id": REPLAY_RUN_ID,
        "messages": [],
        "sender": "",
        "macro_scan_summary": "",
    }
    initial_state.update({field: "" for field in REPORT_FIELDS.values()})
    initial_state.update({summary_key: "" for _, summary_key in SUMMARY_NODES.values()})

    result = ScannerGraphSetup(agents).setup_graph().invoke(initial_state)

    assert len(summary_sources_seen) == len(SUMMARY_NODES)
    for summary_key in (summary_key for _, summary_key in SUMMARY_NODES.values()):
        assert result[summary_key].startswith("- replay | Scanner source:")
        assert "[NO_EVIDENCE]" not in result[summary_key]
    assert json.loads(result["macro_scan_summary"])["executive_summary"] == "Replay synthesis"
    assert macro_prompts, "Macro synthesis was not reached."
