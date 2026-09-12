"""The CLI path must use the persistent decision log.

``store_decision`` / ``get_past_context`` were only reachable from
``TradingAgentsGraph.propagate()``, so the documented "decision log is always
on" behaviour never happened for the ``tradingagents`` CLI (the primary entry
point): no decision was written and the Portfolio Manager prompt never carried
prior lessons. These tests cover the shared lifecycle methods and that
``run_analysis`` actually calls them.

The sibling fix for ``--checkpoint`` (#1249) had the same shape: logic that
lived only in ``propagate()`` was a no-op on the CLI.
"""

from __future__ import annotations

import pytest

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _bare_graph(tmp_path):
    """A graph without ``__init__`` (no LLM clients), wired to a temp log."""
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"memory_log_path": str(tmp_path / "trading_memory.md")}
    graph.memory_log = TradingMemoryLog(graph.config)
    graph.ticker = "NVDA"
    return graph


@pytest.mark.unit
def test_record_decision_appends_a_pending_entry(tmp_path):
    graph = _bare_graph(tmp_path)
    graph.record_decision(
        "NVDA", "2026-01-10", {"final_trade_decision": "Rating: Buy\n\nBuy NVDA."}
    )
    entries = graph.memory_log.load_entries()
    assert [e["ticker"] for e in entries] == ["NVDA"]
    assert entries[0]["pending"] is True
    assert entries[0]["rating"] == "Buy"


@pytest.mark.unit
def test_record_decision_skips_a_run_with_no_decision(tmp_path):
    graph = _bare_graph(tmp_path)
    graph.record_decision("NVDA", "2026-01-10", {})  # interrupted stream
    assert graph.memory_log.load_entries() == []


@pytest.mark.unit
def test_prepare_memory_context_carries_resolved_lessons(tmp_path):
    graph = _bare_graph(tmp_path)
    log = graph.memory_log
    log.store_decision("NVDA", "2026-01-05", "Rating: Buy\nold call")
    log.update_with_outcome(
        "NVDA", "2026-01-05", 0.01, 0.005, 5, "great trade", "2026-01-12"
    )
    context = graph.prepare_memory_context("NVDA", "2026-02-01")
    assert "great trade" in context


class _FakePropagator:
    def __init__(self):
        self.initial_state_kwargs = None

    def create_initial_state(self, ticker, trade_date, asset_type="stock",
                             past_context="", instrument_context=""):
        self.initial_state_kwargs = {
            "ticker": ticker,
            "trade_date": trade_date,
            "past_context": past_context,
            "instrument_context": instrument_context,
        }
        return {"messages": [], "company_of_interest": ticker}

    def get_graph_args(self, callbacks=None):
        return {}


class _FakeGraph:
    def __init__(self, *a, **k):
        self.propagator = _FakePropagator()
        self.graph = self  # so graph.graph.stream(...) resolves
        self.past_context = "LESSON: the prior NVDA call worked"
        self.prepared_for = None
        self.recorded = []

    def prepare_memory_context(self, ticker, trade_date):
        self.prepared_for = (ticker, trade_date)
        return self.past_context

    def record_decision(self, ticker, trade_date, final_state):
        self.recorded.append((ticker, trade_date, final_state))

    def resolve_instrument_context(self, ticker, asset_type="stock"):
        return f"instrument: {ticker}"

    def begin_checkpoint(self, *a, **k):
        return None

    def checkpoint_input(self, state):
        return state

    def clear_checkpoint_on_success(self, *a, **k):
        pass

    def end_checkpoint(self):
        pass

    def stream(self, graph_input, **kwargs):
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

    def update_report_section(self, section_name, content):
        self.report_sections[section_name] = content

    def update_agent_status(self, agent, status):
        self.agent_status[agent] = status


@pytest.mark.unit
def test_cli_run_reads_and_writes_the_decision_log(tmp_path, monkeypatch):
    import cli.main as m
    from cli.models import AnalystType

    fake_graph = _FakeGraph()

    monkeypatch.setattr(m, "TradingAgentsGraph", lambda *a, **k: fake_graph)
    monkeypatch.setattr(m, "message_buffer", _FakeBuffer())
    monkeypatch.setattr(m, "create_layout", lambda: None)
    monkeypatch.setattr(m, "update_display", lambda *a, **k: None)
    monkeypatch.setattr(m, "Live", _NullLive)
    monkeypatch.setattr(
        m,
        "get_user_selections",
        lambda: {
            "ticker": "NVDA",
            "analysis_date": "2026-01-10",
            "analysts": [AnalystType.MARKET],
            "asset_type": "stock",
        },
    )
    monkeypatch.setattr(
        m,
        "_build_run_config",
        lambda selections, checkpoint: {
            "data_cache_dir": str(tmp_path / "cache"),
            "results_dir": str(tmp_path / "results"),
        },
    )
    monkeypatch.setattr(m.typer, "prompt", lambda *a, **k: "N")

    m.run_analysis()

    # Prior lessons must reach the initial state, and the finished run must be
    # recorded — the two things missing on the CLI path before.
    assert fake_graph.prepared_for == ("NVDA", "2026-01-10")
    assert (
        fake_graph.propagator.initial_state_kwargs["past_context"]
        == fake_graph.past_context
    )
    assert len(fake_graph.recorded) == 1
    ticker, trade_date, final_state = fake_graph.recorded[0]
    assert (ticker, trade_date) == ("NVDA", "2026-01-10")
    assert final_state["final_trade_decision"].startswith("Rating: Buy")
