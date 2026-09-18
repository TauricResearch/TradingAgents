"""The CLI must use the decision log the same way propagate() does.

The CLI streams the graph itself instead of calling propagate(), so memory steps
that lived only in propagate() never ran on the primary entry point: pending
decisions were not settled, the Portfolio Manager got no past context, and the
finished decision was not recorded. Both paths now build their initial state and
record their decision through the same graph methods.
"""

from __future__ import annotations

import pytest

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _bare_graph(tmp_path):
    """A graph without __init__ (no LLM clients), wired to a temp log."""
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"memory_log_path": str(tmp_path / "trading_memory.md")}
    graph.memory_log = TradingMemoryLog(graph.config)
    return graph


@pytest.mark.unit
def test_create_run_state_settles_pending_and_carries_context(tmp_path, monkeypatch):
    from tradingagents.graph.propagation import Propagator

    graph = _bare_graph(tmp_path)
    graph.propagator = Propagator()
    settled = []
    monkeypatch.setattr(graph, "_resolve_pending_entries", settled.append, raising=False)
    monkeypatch.setattr(graph, "resolve_instrument_context", lambda t, a="stock", d=None: f"id:{t}", raising=False)
    monkeypatch.setattr(graph, "_memory_as_of", lambda d: d, raising=False)
    graph.memory_log.store_decision("NVDA", "2026-01-05", "Rating: Buy\nold call")
    graph.memory_log.update_with_outcome("NVDA", "2026-01-05", 0.01, 0.005, 5, "great trade", "2026-01-12")

    state = graph.create_run_state("NVDA", "2026-02-01")

    assert settled == ["NVDA"]
    assert "great trade" in state["past_context"]
    assert state["instrument_context"] == "id:NVDA"
    assert state["company_of_interest"] == "NVDA"


@pytest.mark.unit
def test_record_decision_appends_a_pending_entry(tmp_path):
    graph = _bare_graph(tmp_path)
    graph.record_decision("NVDA", "2026-01-10", {"final_trade_decision": "Rating: Buy\n\nBuy NVDA."})
    entries = graph.memory_log.load_entries()
    assert [(e["ticker"], e["pending"], e["rating"]) for e in entries] == [("NVDA", True, "Buy")]


@pytest.mark.unit
def test_record_decision_skips_a_run_without_a_decision(tmp_path):
    graph = _bare_graph(tmp_path)
    graph.record_decision("NVDA", "2026-01-10", {})
    assert graph.memory_log.load_entries() == []


# --- the CLI path ----------------------------------------------------------------

class _FakeGraph:
    """Records the lifecycle calls run_analysis makes."""

    def __init__(self):
        self.calls = []
        self.graph = self
        self.propagator = self

    def create_run_state(self, ticker, trade_date, asset_type="stock", portfolio=None):
        self.calls.append(("create_run_state", ticker, trade_date))
        return {"messages": [], "company_of_interest": ticker}

    def process_signal(self, text):
        from tradingagents.graph.signal_processing import SignalProcessor
        return SignalProcessor.process_signal(None, text)

    def record_decision(self, ticker, trade_date, final_state):
        self.calls.append(("record_decision", ticker, trade_date, final_state.get("final_trade_decision")))

    def get_graph_args(self, callbacks=None):
        return {}

    def begin_checkpoint(self, *a, **k):
        return None

    def checkpoint_input(self, state):
        return state

    def clear_checkpoint_on_success(self, *a, **k):
        self.calls.append(("clear_checkpoint",))

    def end_checkpoint(self):
        pass

    def stream(self, graph_input, **kwargs):
        yield {"messages": [], "market_report": "M"}
        yield {"messages": [], "final_trade_decision": "Rating: Buy\n\nBuy NVDA."}


class _NullLive:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeBuffer:
    def __init__(self):
        self.messages = []
        self.tool_calls = []
        self.report_sections = {}
        self.agent_status = {}
        self.selected_analysts = []
        self._processed_message_ids = set()

    def init_for_analysis(self, selected_analysts):
        self.selected_analysts = [a.lower() for a in selected_analysts]

    def add_message(self, kind, content):
        self.messages.append((0.0, kind, content))

    def add_tool_call(self, name, args):
        self.tool_calls.append((0.0, name, args))

    def update_report_section(self, *a):
        pass

    def update_agent_status(self, agent, status):
        self.agent_status[agent] = status


@pytest.mark.unit
def test_cli_run_uses_the_decision_log_like_propagate(tmp_path, monkeypatch):
    import cli.main as m
    from cli.models import AnalystType

    fake = _FakeGraph()
    monkeypatch.setattr(m, "TradingAgentsGraph", lambda *a, **k: fake)
    monkeypatch.setattr(m, "message_buffer", _FakeBuffer())
    monkeypatch.setattr(m, "create_layout", lambda: None)
    monkeypatch.setattr(m, "update_display", lambda *a, **k: None)
    monkeypatch.setattr(m, "Live", _NullLive)
    monkeypatch.setattr(m, "get_user_selections", lambda: {
        "ticker": "NVDA", "analysis_date": "2026-01-10",
        "analysts": [AnalystType.MARKET], "asset_type": "stock",
    })
    monkeypatch.setattr(m, "_build_run_config", lambda selections, checkpoint: {
        "data_cache_dir": str(tmp_path / "cache"), "results_dir": str(tmp_path / "results"),
    })
    monkeypatch.setattr(m.typer, "prompt", lambda *a, **k: "N")

    m.run_analysis()

    assert fake.calls == [
        ("create_run_state", "NVDA", "2026-01-10"),
        # The decision is recorded from the merged stream, before the checkpoint
        # is cleared, matching propagate().
        ("record_decision", "NVDA", "2026-01-10", "Rating: Buy\n\nBuy NVDA."),
        ("clear_checkpoint",),
    ]
