"""Tests for F10: backend wiring of scanner_graph_facts into the pipeline.

All tests use monkeypatching — no live LLM or real disk scanner runs.
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from tradingagents.graph.scanner_facts.schema import SCHEMA_VERSION


SCAN_DATE = "2026-04-16"
RUN_ID = "TESTRUN"


def _minimal_facts():
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_date": SCAN_DATE,
        "run_id": RUN_ID,
        "source_dir": "reports/daily/2026-04-16/TESTRUN/market",
        "global_regime": {"summary": "Risk-On", "bullets": [], "source": "macro_scan_summary.json"},
        "nodes": [
            {"id": "ON", "type": "Ticker", "label": "ON", "aliases": [], "provenance": ["smart_money_summary.md"], "evidence": ["ON observed"], "confidence": 0.95},
            {"id": "Technology", "type": "Sector", "label": "Technology", "aliases": [], "provenance": ["sector_summary.md"], "evidence": ["Tech sector"], "confidence": 0.90},
        ],
        "edges": [
            {"source": "ON", "relation": "BELONGS_TO", "target": "Technology", "polarity": "", "provenance": "smart_money_summary.md", "evidence": "ON | Technology", "confidence": 0.90},
        ],
        "metadata": {"node_count": 2, "edge_count": 1, "generated_at": "2026-04-16T00:00:00Z", "inputs": []},
    }


def test_macro_scan_summary_json_written_to_market_dir(tmp_path):
    """_save_scan_outputs must write macro_scan_summary.json to the flat market dir."""
    import asyncio
    from agent_os.backend.services.langgraph_engine import LangGraphEngine

    engine = LangGraphEngine.__new__(LangGraphEngine)
    engine.config = {}

    market_dir = tmp_path / "reports" / "daily" / SCAN_DATE / RUN_ID / "market"
    market_dir.mkdir(parents=True)

    final_state = {
        "macro_scan_summary": json.dumps({
            "timeframe": "2026-04-16",
            "executive_summary": "Risk-On regime.",
            "key_themes": [],
            "stocks_to_investigate": [],
        }),
        "gatekeeper_summary": "",
        "geopolitical_summary": "",
        "market_movers_summary": "",
        "sector_summary": "",
        "factor_alignment_summary": "",
        "drift_opportunities_summary": "",
        "smart_money_summary": "",
        "industry_deep_dive_summary": "",
    }

    mock_store = MagicMock()
    mock_store.save_scan.return_value = None

    with patch("agent_os.backend.services.langgraph_engine.get_market_dir", return_value=market_dir), \
         patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
         patch("agent_os.backend.services.langgraph_engine.ensure_scanner_graph_facts") as mock_ensure:
        mock_ensure.return_value = market_dir / "scanner_graph_facts.json"

        async def run():
            events = []
            async for evt in engine._save_scan_outputs(final_state, SCAN_DATE, RUN_ID, mock_store):
                events.append(evt)
            return events

        asyncio.run(run())

    assert (market_dir / "macro_scan_summary.json").exists(), \
        "macro_scan_summary.json must be written to flat market dir"


def test_ensure_scanner_graph_facts_called_after_save(tmp_path):
    """ensure_scanner_graph_facts must be called during _save_scan_outputs."""
    import asyncio
    from agent_os.backend.services.langgraph_engine import LangGraphEngine

    engine = LangGraphEngine.__new__(LangGraphEngine)
    engine.config = {}

    market_dir = tmp_path / "reports" / "daily" / SCAN_DATE / RUN_ID / "market"
    market_dir.mkdir(parents=True)

    final_state = {
        "macro_scan_summary": json.dumps({
            "timeframe": SCAN_DATE,
            "executive_summary": "Risk-On.",
            "key_themes": [],
            "stocks_to_investigate": [],
        }),
        **{k: "" for k in ["gatekeeper_summary", "geopolitical_summary", "market_movers_summary",
                            "sector_summary", "factor_alignment_summary", "drift_opportunities_summary",
                            "smart_money_summary", "industry_deep_dive_summary"]},
    }

    mock_store = MagicMock()

    with patch("agent_os.backend.services.langgraph_engine.get_market_dir", return_value=market_dir), \
         patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
         patch("agent_os.backend.services.langgraph_engine.ensure_scanner_graph_facts") as mock_ensure:
        mock_ensure.return_value = market_dir / "scanner_graph_facts.json"

        async def run():
            async for _ in engine._save_scan_outputs(final_state, SCAN_DATE, RUN_ID, mock_store):
                pass

        asyncio.run(run())

    mock_ensure.assert_called_once_with(scan_date=SCAN_DATE, run_id=RUN_ID)


def test_run_pipeline_raises_when_graph_facts_missing(tmp_path):
    """run_pipeline must raise FileNotFoundError when scanner_graph_facts.json is absent."""
    import asyncio
    from agent_os.backend.services.langgraph_engine import LangGraphEngine

    engine = LangGraphEngine.__new__(LangGraphEngine)
    engine.config = {}
    engine._run_loggers = {}
    engine._event_mapper = MagicMock()
    engine._event_mapper.register_run.return_value = None
    engine._event_mapper.unregister_run.return_value = None
    engine._event_mapper.map_event.return_value = None

    # graph_facts_path does not exist → should raise FileNotFoundError
    with patch("agent_os.backend.services.langgraph_engine.get_scanner_graph_facts_path",
               return_value=tmp_path / "nonexistent" / "scanner_graph_facts.json"), \
         patch("tradingagents.report_paths.get_scanner_graph_facts_path",
               return_value=tmp_path / "nonexistent" / "scanner_graph_facts.json"), \
         patch("agent_os.backend.services.langgraph_engine.TradingAgentsGraph"):

        async def run():
            with pytest.raises(FileNotFoundError) as exc_info:
                async for evt in engine.run_pipeline("TESTRUN", {
                    "ticker": "ON", "date": SCAN_DATE, "run_id": RUN_ID,
                }):
                    pass
            error_msg = str(exc_info.value)
            assert "rebuild" in error_msg.lower() or "scanner_graph_facts" in error_msg

        asyncio.run(run())
