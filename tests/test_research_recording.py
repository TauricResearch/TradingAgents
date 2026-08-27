import json
from unittest.mock import MagicMock

import pytest

from cli.main import _persist_streamed_final_state, _prepare_streaming_initial_state
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.reporting import write_report_tree


def _research_result():
    return {
        "schema_version": "research-decision-v1",
        "prompt_version": "evidence-contract-v1",
        "ticker": "AAPL",
        "analysis_date": "2026-01-02",
        "analysis_cutoff": "2026-01-02",
        "model_provider": "fixture",
        "models": {"quick": "q", "deep": "d"},
        "rating": "Buy",
        "decision_status": "No Trade",
        "research_only": True,
        "time_horizon": "20 trading days",
        "expected_return_low": -0.03,
        "expected_return_high": 0.08,
        "confidence": 0.4,
        "data_quality": "Low",
        "invalidation_conditions": ["Guidance is not verified"],
        "key_risks": ["Earnings miss"],
        "evidence": [{"claim": "x"}],
        "safety_gate": {"passed": False, "reasons": ["confidence is too low"]},
    }


@pytest.mark.unit
def test_report_tree_writes_machine_readable_research_result(tmp_path):
    state = {
        "risk_debate_state": {"judge_decision": "**Rating**: Buy"},
        "research_result": _research_result(),
    }
    complete = write_report_tree(state, "AAPL", tmp_path)
    record = json.loads((tmp_path / "research_result.json").read_text())
    assert record["decision_status"] == "No Trade"
    assert record["research_only"] is True
    assert "## VI. Research Audit Record" in complete.read_text()


@pytest.mark.unit
def test_memory_log_round_trips_compact_research_metadata_without_raw_config(tmp_path):
    log_path = tmp_path / "memory.md"
    log = TradingMemoryLog({"memory_log_path": str(log_path)})
    result = _research_result()
    result["api_key"] = "must-not-be-written"
    result["raw_provider_payload"] = "x" * 10_000
    log.store_decision("AAPL", "2026-01-02", "Rating: Buy\nResearch only.", result)
    entry = log.load_entries()[0]
    metadata = entry["research_result"]
    assert metadata["decision_status"] == "No Trade"
    assert metadata["confidence"] == 0.4
    assert metadata["evidence_count"] == 1
    raw = log_path.read_text()
    assert "must-not-be-written" not in raw
    assert "raw_provider_payload" not in raw


@pytest.mark.unit
def test_cli_streaming_path_reads_and_persists_research_memory(tmp_path):
    graph = MagicMock()
    graph.resolve_instrument_context.return_value = "Ticker: AAPL"
    graph.memory_log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
    graph.memory_log.store_decision(
        "AAPL",
        "2026-01-01",
        "Rating: Hold\nPrior research.",
    )
    graph.memory_log.update_with_outcome(
        "AAPL",
        "2026-01-01",
        raw_return=0.01,
        alpha_return=0.0,
        holding_days=5,
        reflection="Waited appropriately.",
    )
    graph.propagator.create_initial_state.return_value = {"initial": True}
    selections = {
        "ticker": "AAPL",
        "asset_type": "stock",
        "analysis_date": "2026-01-02",
    }

    initial = _prepare_streaming_initial_state(graph, selections)
    assert initial == {"initial": True}
    kwargs = graph.propagator.create_initial_state.call_args.kwargs
    assert "Waited appropriately" in kwargs["past_context"]

    final_state = {
        "final_trade_decision": "Rating: Buy\nResearch only.",
        "research_result": _research_result(),
    }
    _persist_streamed_final_state(graph, selections, final_state)
    graph._log_state.assert_called_once_with("2026-01-02", final_state)
    entries = graph.memory_log.load_entries()
    assert len(entries) == 2
    assert entries[-1]["research_result"]["decision_status"] == "No Trade"
