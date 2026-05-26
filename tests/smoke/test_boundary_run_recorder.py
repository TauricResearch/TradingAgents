import pytest
from unittest.mock import patch


pytestmark = pytest.mark.smoke


def test_run_recorder_node_fires_for_every_persona_in_deepdive(tmp_path, monkeypatch):
    """Verify the Run Recorder node is invoked by the compiled graph for
    each persona. Uses a real graph compile but with the engine's propagate
    monkey-patched to short-circuit after the Run Recorder runs."""
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))

    invocations = []
    from tradingagents.graph.run_recorder import RunRecorder

    original_record = RunRecorder.record

    def spying_record(self, state):
        invocations.append((self._run_id, self._persona_id))
        return original_record(self, state)

    # Patch propagate to write a minimal final state to disk + DB rather than
    # invoking the full LangGraph. This isolates "did the Run Recorder fire?"
    # from "did the LLM produce real content?".
    # Signature must match the real propagate: (self, company_name, trade_date, asset_type="stock")
    # cli/deepdive.py calls graph.propagate(ticker, trade_date) positionally.
    def stub_propagate(self, company_name, trade_date, asset_type="stock"):
        final_state = {
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "trade_date": trade_date,
            "market_report": "stub", "sentiment_report": "stub",
            "news_report": "stub", "fundamentals_report": "stub",
            "derivatives_report": "",
            "investment_plan": "stub",
            "trader_investment_plan": "FINAL TRANSACTION PROPOSAL: **HOLD**",
            "final_trade_decision": "HOLD",
            "investment_debate_state": {"history": "stub"},
            "risk_debate_state": {"history": "stub"},
        }
        # Mark the run started + emit the recorder pass.
        from datetime import datetime, timezone
        self.run_recorder.start(ticker=company_name,
                                started_ts=datetime.now(timezone.utc).isoformat())
        self.run_recorder.record(final_state)
        return final_state

    from tradingagents.graph.trading_graph import TradingAgentsGraph
    with patch.object(RunRecorder, "record", spying_record), \
         patch.object(TradingAgentsGraph, "propagate", stub_propagate):
        from cli.deepdive import run_deepdive
        # Also bypass the Secretary's LLM by patching the synthesis.
        with patch("tradingagents.secretary.service.synthesize_brief", return_value={
            "consensus": "x", "divergence": "y", "recommendation": "HOLD", "raw": "..."
        }):
            # parallel=False: sequential execution makes invocations list deterministic.
            run_deepdive(ticker="AAPL", trade_date="2026-05-25", parallel=False)

    # Each persona must fire exactly once — guard against both missing and duplicate fires.
    assert len(invocations) == 3, \
        f"Expected 3 Run Recorder invocations (one per persona), got {len(invocations)}: {invocations}"
    persona_ids_seen = {pid for _, pid in invocations}
    assert persona_ids_seen == {"macro", "value", "momentum"}, \
        f"Run Recorder fired for {persona_ids_seen}, not all three personas"
