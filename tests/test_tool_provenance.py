from __future__ import annotations

import json
from uuid import uuid4

from langchain_core.messages import ToolMessage

from tradingagents.agents.utils.tool_provenance import create_tool_provenance_capture_node
from tradingagents.agents.utils.recommendation_audit import (
    build_pre_synthesis_scope_audit,
    build_recommendation_scorecard,
)
from tradingagents.agents.claims import build_claim_graph
from tradingagents.agents.source_registry import build_source_registry, validate_source_citations
from tradingagents.agents.skills import build_skill_registry
from tradingagents_service.provenance import (
    RunTelemetryRecorder,
    ToolProvenanceRecorder,
    summarize_run_telemetry,
    write_run_telemetry,
    write_tool_provenance,
)
from tradingagents_service.quality import assess_shadow_run_quality


def test_tool_provenance_recorder_captures_raw_tool_output(tmp_path) -> None:
    recorder = ToolProvenanceRecorder(shadow_run_id="run-123")
    run_id = uuid4()

    recorder.on_tool_start(
        {"name": "get_stock_data"},
        "NVDA",
        run_id=run_id,
        inputs={"ticker": "NVDA", "date": "2026-01-15"},
    )
    recorder.on_tool_end({"close": [100.0, 101.5]}, run_id=run_id)

    assert len(recorder.records) == 1
    record = recorder.records[0]
    assert record["source_id"] == "RAW-TOOL-0001"
    assert record["tool_name"] == "get_stock_data"
    assert record["input"]["ticker"] == "NVDA"
    assert record["output"]["close"] == [100.0, 101.5]
    assert record["shadow_run_id"] == "run-123"
    assert record["tool_args_hash"]
    assert record["latency_ms"] is not None
    assert len(record["output_sha256"]) == 64

    manifest = write_tool_provenance(recorder.records, tmp_path, shadow_run_id="run-123")

    assert manifest is not None
    assert manifest["record_count"] == 1
    assert manifest["source_ids"] == ["RAW-TOOL-0001"]
    assert manifest["shadow_run_id"] == "run-123"
    jsonl_path = tmp_path / "raw_tool_outputs.jsonl"
    manifest_path = tmp_path / "raw_tool_outputs_manifest.json"
    assert jsonl_path.exists()
    assert manifest_path.exists()
    assert json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])["source_id"] == "RAW-TOOL-0001"


def test_run_telemetry_records_llm_and_tool_usage(tmp_path) -> None:
    recorder = RunTelemetryRecorder(shadow_run_id="run-telemetry-1")
    run_id = uuid4()

    recorder.on_llm_start(
        {"name": "PortfolioManager", "kwargs": {"model": "gpt-4o"}},
        ["Explain the recommendation."],
        run_id=run_id,
        metadata={"provider": "openai", "model": "gpt-4o"},
    )
    response = type(
        "LLMResponse",
        (),
        {
            "generations": [[type("Generation", (), {"text": "Buy"})()]],
            "llm_output": {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
        },
    )()
    recorder.on_llm_end(response, run_id=run_id)

    summary = summarize_run_telemetry(recorder.records)
    assert summary["shadow_run_id"] == "run-telemetry-1"
    assert summary["llm_call_count"] == 1
    assert summary["token_total"] == 15
    assert summary["records"][0]["prompt_hash"]
    assert summary["records"][0]["response_hash"]

    manifest = write_run_telemetry(recorder.records, tmp_path, shadow_run_id="run-telemetry-1")
    assert manifest is not None
    assert manifest["shadow_run_id"] == "run-telemetry-1"
    assert (tmp_path / "run_telemetry.jsonl").exists()
    assert (tmp_path / "run_telemetry_manifest.json").exists()


def test_quality_source_summary_includes_raw_tool_provenance() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Hold. Momentum is mixed [SRC-MARKET-1] [RAW-TOOL-0001].",
        final_state={
            "market_report": "Market analyst report shows mixed momentum.",
            "source_objects": [{"source_id": "SRC-MARKET-1", "source_type": "market"}],
            "raw_tool_outputs": [
                {
                    "source_id": "RAW-TOOL-0001",
                    "source_type": "raw_tool_output",
                    "tool_name": "get_stock_data",
                    "output_sha256": "a" * 64,
                }
            ],
            "raw_tool_provenance": {
                "record_count": 1,
                "source_ids": ["RAW-TOOL-0001"],
                "tools": ["get_stock_data"],
            },
            "raw_tool_provenance_expected": True,
        },
    )

    assert assessment.source_summary["raw_tool_output_count"] == 1
    assert assessment.source_summary["raw_tool_output_ids"] == ["RAW-TOOL-0001"]
    assert assessment.source_summary["raw_tool_names"] == ["get_stock_data"]
    assert "missing_raw_tool_provenance" not in {finding.code for finding in assessment.findings}


def test_graph_tool_capture_node_adds_raw_tool_sources() -> None:
    node = create_tool_provenance_capture_node("market")
    tool_message = ToolMessage(
        content="date,close\n2026-01-15,100.50\n",
        tool_call_id="call-1",
        name="get_stock_data",
    )

    result = node({"messages": [tool_message], "raw_tool_outputs": [], "raw_tool_seen_ids": []})

    assert result["raw_tool_outputs"][0]["source_id"] == "RAW-TOOL-0001"
    assert result["raw_tool_outputs"][0]["tool_name"] == "get_stock_data"
    assert result["raw_tool_outputs"][0]["content"].startswith("date,close")
    assert len(result["raw_tool_outputs"][0]["output_sha256"]) == 64


def test_quality_fails_when_raw_tool_sources_are_uncited() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Hold. Momentum is mixed [SRC-MARKET-1].",
        final_state={
            "market_report": "Market analyst report shows mixed momentum.",
            "source_objects": [{"source_id": "SRC-MARKET-1", "source_type": "market"}],
            "raw_tool_outputs": [
                {
                    "source_id": "RAW-TOOL-0001",
                    "source_type": "raw_tool_output",
                    "tool_name": "get_stock_data",
                    "output_sha256": "a" * 64,
                }
            ],
        },
    )

    assert assessment.status == "failed"
    assert "missing_raw_tool_citation" in {finding.code for finding in assessment.findings}


def test_quality_warns_when_expected_raw_tool_provenance_missing() -> None:
    final_state = {
        "market_report": "Market analyst report shows mixed momentum.",
        "source_objects": [{"source_id": "SRC-MARKET-1", "source_type": "market"}],
        "raw_tool_provenance_expected": True,
    }
    registry = build_source_registry(final_state)
    final_state["claim_graph"] = build_claim_graph(final_state, registry)
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Hold. Momentum is mixed [SRC-MARKET-1].",
        final_state=final_state,
    )

    assert assessment.status == "failed"
    assert "missing_raw_tool_provenance" in {finding.code for finding in assessment.findings}


def test_recommendation_scorecard_uses_six_named_factors() -> None:
    scorecard = build_recommendation_scorecard(
        {
            "market_report": "Uptrend breakout above resistance with strong momentum and controlled volatility.",
            "news_report": "Positive news beat expectations.",
            "sentiment_report": "Analyst sentiment remains constructive.",
            "fundamentals_report": "Revenue growth and cash flow are improving.",
            "risk_debate_state": {"history": "Risk-controlled and balanced with disciplined hedging."},
            "macro_report": "Stable rates and easing inflation keep the macro backdrop favorable.",
        }
    )

    assert [factor["factor"] for factor in scorecard["factors"]] == [
        "technical_trend",
        "momentum",
        "volatility",
        "news_sentiment",
        "fundamentals",
        "risk_posture",
        "macro_regime",
    ]
    assert scorecard["method"].startswith("claim-backed deterministic audit model")
    assert scorecard["factors"][0]["inputs"]["matched_positive_terms"] == [
        "uptrend",
        "breakout",
        "above resistance",
    ]
    assert scorecard["factors"][0]["rationale"].startswith("Technical trend: score=")
    assert scorecard["suggested_rating"] in {"Buy", "Overweight", "Hold", "Underweight", "Sell"}


def test_pre_synthesis_scope_audit_detects_unrelated_report_entity() -> None:
    audit = build_pre_synthesis_scope_audit(
        "AAPL",
        {"news_report": "Apple demand is stable. Marvell also reported strong results."},
    )

    assert audit["status"] == "failed"
    assert audit["findings"][0]["code"] == "pre_synthesis_unrelated_entity"


def test_source_registry_and_claim_graph_build_structured_evidence() -> None:
    final_state = {
        "market_report": "Momentum remains strong [SRC-MARKET-1]. Momentum is weak and bearish [RAW-TOOL-0001].",
        "news_report": "Positive news beat expectations [SRC-NEWS-1].",
        "sentiment_report": "Analyst sentiment remains constructive.",
        "fundamentals_report": "Revenue growth and cash flow are improving.",
        "source_objects": [
            {"source_id": "SRC-MARKET-1", "source_type": "market", "state_key": "market_report", "label": "Market analyst report"},
            {"source_id": "SRC-NEWS-1", "source_type": "news", "state_key": "news_report", "label": "News analyst report"},
        ],
        "raw_tool_outputs": [
            {"source_id": "RAW-TOOL-0001", "tool_name": "get_stock_data", "output": "volatility is elevated"}
        ],
    }
    registry = build_source_registry(final_state)
    claims = build_claim_graph(final_state, registry)
    skills = build_skill_registry(final_state, registry, claims)

    assert "SRC-MARKET-1" in registry["source_index"]
    assert "RAW-TOOL-0001" in registry["source_index"]
    assert registry["source_summary"]["source_count"] >= 3
    assert claims["claim_count"] >= 4
    assert set(claims["claim_source_ids"]) >= {"RAW-TOOL-0001", "SRC-MARKET-1", "SRC-NEWS-1"}
    assert claims["claim_summary"]["claim_count"] == claims["claim_count"]
    assert claims["claim_summary"]["claim_source_count"] == len(claims["claim_source_ids"])
    assert claims["claim_summary"]["counterevidence_claim_count"] >= 1
    assert claims["claim_summary"]["source_backed_claim_count"] == claims["claim_count"]
    market_claim = next(claim for claim in claims["claim_objects"] if claim["text"].startswith("Momentum remains strong"))
    bearish_claim = next(claim for claim in claims["claim_objects"] if claim["text"].startswith("Momentum is weak"))
    assert market_claim["source_ids"] == ["SRC-MARKET-1"]
    assert market_claim["evidence_type"] == "inline_citation"
    assert bearish_claim["source_ids"] == ["RAW-TOOL-0001"]
    assert bearish_claim["counterevidence_claim_ids"]
    assert "RAW-TOOL-0001" in claims["source_registry"]["source_claim_index"]
    assert bearish_claim["claim_id"] in claims["source_registry"]["source_claim_index"]["RAW-TOOL-0001"]
    assert bearish_claim["claim_id"] in claims["source_registry"]["source_index"]["RAW-TOOL-0001"]["claim_ids"]
    assert set(claims["source_registry"]["claim_source_ids"]) == set(claims["claim_source_ids"])
    assert len(skills["skills"]) == 7
    assert validate_source_citations(registry, ["SRC-MARKET-1"]) == []
    assert validate_source_citations(registry, ["SRC-UNKNOWN-1"]) == ["SRC-UNKNOWN-1"]
