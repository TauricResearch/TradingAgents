"""The CLI must use the memory log the same way propagate() does.

The CLI streams the graph itself instead of calling propagate(), so memory steps
that lived only in propagate() never ran on the primary entry point: pending
decisions were not settled, the Portfolio Manager got no past context, and the
finished decision was not recorded. Both paths now build their initial state and
record their decision through the same graph methods.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import cli.run as cli_run
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.memory import TradingMemoryLog


def _bare_graph(tmp_path):
    """A graph without __init__ (no LLM clients), wired to a temp log."""
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"memory_log_path": str(tmp_path / "trading_memory.md")}
    graph.memory_log = TradingMemoryLog(graph.config)
    graph._log_state = lambda *a: None   # these tests are about the memory log
    return graph


@pytest.mark.unit
def test_create_run_state_settles_pending_and_carries_context(tmp_path, monkeypatch):
    from tradingagents.graph.propagation import Propagator

    graph = _bare_graph(tmp_path)
    graph.propagator = Propagator()
    settled = []
    monkeypatch.setattr(graph, "settle_pending", settled.append, raising=False)
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

    def __init__(self, resuming=None):
        self.calls = []
        self.graph = self
        self.propagator = self
        self.resuming = resuming      # None: checkpointing off
        self._resuming = False

    def create_run_state(self, ticker, trade_date, asset_type="stock", portfolio=None):
        self.calls.append(("create_run_state", ticker, trade_date))
        return {"messages": [], "company_of_interest": ticker}

    def record_decision(self, ticker, trade_date, final_state):
        self.calls.append(("record_decision", ticker, trade_date, final_state.get("final_trade_decision")))

    def get_graph_args(self, callbacks=None):
        return {}

    def begin_checkpoint(self, *a, **k):
        self._resuming = bool(self.resuming)
        return None if self.resuming is None else "thread"

    def checkpoint_input(self, state):
        return state

    def clear_checkpoint_on_success(self, *a, **k):
        self.calls.append(("clear_checkpoint",))

    def end_checkpoint(self):
        pass

    def stream_run(self, graph_input, **kwargs):
        yield [], {"messages": [], "market_report": "M"}
        yield [], {"messages": [], "final_trade_decision": "Rating: Buy\n\nBuy NVDA.", "final_rating": "Buy"}


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


def _run_cli(monkeypatch, tmp_path, fake):
    """Drive run_analysis against ``fake``; returns the message buffer."""
    import cli.main as m
    from cli.models import AnalystType

    buffer = _FakeBuffer()
    monkeypatch.setattr(cli_run, "TradingAgentsGraph", lambda *a, **k: fake)
    monkeypatch.setattr(cli_run, "message_buffer", buffer)
    monkeypatch.setattr(cli_run, "create_layout", lambda: None)
    monkeypatch.setattr(cli_run, "update_display", lambda *a, **k: None)
    monkeypatch.setattr(cli_run, "Live", _NullLive)
    monkeypatch.setattr(cli_run, "get_user_selections", lambda flags=None: {
        "ticker": "NVDA", "analysis_date": "2026-01-10",
        "analysts": [AnalystType.MARKET], "asset_type": "stock",
    })
    monkeypatch.setattr(cli_run, "_build_run_config", lambda selections, checkpoint: {
        "data_cache_dir": str(tmp_path / "cache"), "results_dir": str(tmp_path / "results"),
    })
    monkeypatch.setattr(m.typer, "prompt", lambda *a, **k: "N")
    cli_run.run_analysis()
    return buffer


@pytest.mark.unit
def test_cli_run_uses_the_memory_log_like_propagate(tmp_path, monkeypatch):
    fake = _FakeGraph()
    _run_cli(monkeypatch, tmp_path, fake)

    assert fake.calls == [
        ("create_run_state", "NVDA", "2026-01-10"),
        # The decision is recorded from the merged stream, before the checkpoint
        # is cleared, matching propagate().
        ("record_decision", "NVDA", "2026-01-10", "Rating: Buy\n\nBuy NVDA."),
        ("clear_checkpoint",),
    ]


@pytest.mark.unit
@pytest.mark.parametrize("resuming, said", [(True, "resuming"), (False, "starting fresh")])
def test_the_cli_run_says_whether_it_resumed(tmp_path, monkeypatch, resuming, said):
    """The README promises the run view tells a resumed run from a fresh one."""
    buffer = _run_cli(monkeypatch, tmp_path, _FakeGraph(resuming=resuming))

    assert any(said in text.lower() for _, kind, text in buffer.messages if kind == "System")


@pytest.mark.unit
def test_a_run_without_checkpointing_says_nothing_about_resuming(tmp_path, monkeypatch):
    buffer = _run_cli(monkeypatch, tmp_path, _FakeGraph())

    assert not any("resum" in text.lower() or "fresh" in text.lower() for _, _, text in buffer.messages)


@pytest.mark.unit
def test_recording_a_run_writes_its_state_log(tmp_path):
    """The CLI records a run through record_decision, so the state log is written there."""
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path), "llm_provider": "openai", "deep_think_llm": "d",
                    "quick_think_llm": "q", "max_debate_rounds": 1, "max_risk_discuss_rounds": 1,
                    "output_language": "English", "data_vendors": {}, "tool_vendors": {}}
    graph.selected_analysts = ("market",)
    graph.memory_log = TradingMemoryLog({"memory_log_path": str(tmp_path / "m.md")})
    state = {"company_of_interest": "NVDA", "trade_date": "2026-09-23", "market_report": "M",
             "sentiment_report": "", "news_report": "", "fundamentals_report": "",
             "investment_debate_state": {"bull_history": "", "bear_history": "", "history": "",
                                         "current_response": ""},
             "trader_investment_plan": "T", "investment_plan": "P",
             "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                                   "neutral_history": "", "history": ""},
             "final_trade_decision": "**Rating**: Hold", "final_rating": "Hold"}

    graph.record_decision("NVDA", "2026-09-23", state)

    assert list(tmp_path.glob("NVDA/TradingAgentsStrategy_logs/full_states_log_2026-09-23.json"))


@pytest.mark.unit
@pytest.mark.parametrize("save_fails", [False, True])
def test_flag_cli_resumes_and_clears_only_after_report_saved(tmp_path, monkeypatch, save_fails):
    import cli.main as m
    from cli.models import AnalystType

    class ResumedGraph(_FakeGraph):
        config = {"checkpoint_enabled": True}

        def resolve_instrument_context(self, *args):
            return "instrument"

        def create_initial_state(self, *args, **kwargs):
            return {"messages": []}

        @contextmanager
        def checkpoint_scope(self, *args):
            self.calls.append(("begin",))
            try:
                yield "saved-thread"
            finally:
                self.calls.append(("end",))

        def checkpoint_input(self, state):
            return None

        def stream_run(self, graph_input, **kwargs):
            assert graph_input is None
            assert kwargs["config"]["configurable"]["thread_id"] == "saved-thread"
            yield [], {"final_trade_decision": "Rating: Buy\nPrice Target: 120"}

        def get_state(self, config):
            assert config["configurable"]["thread_id"] == "saved-thread"
            return SimpleNamespace(values={
                "market_report": "saved analyst work", "trader_investment_plan": "saved trade",
                "final_trade_decision": "Rating: Buy\nPrice Target: 120",
                "risk_debate_state": {"judge_decision": "Rating: Buy\nPrice Target: 120"},
            })

    fake = ResumedGraph()
    monkeypatch.setattr(m, "TradingAgentsGraph", lambda *a, **k: fake)
    monkeypatch.setattr(m, "message_buffer", _FakeBuffer())
    monkeypatch.setattr(m, "create_layout", lambda: None)
    monkeypatch.setattr(m, "update_display", lambda *a, **k: None)
    monkeypatch.setattr(m, "Live", _NullLive)
    monkeypatch.setattr(m, "_build_run_config", lambda *a: {
        "results_dir": str(tmp_path / "results"), "reports_dir": str(tmp_path / "docs"),
        "deep_think_llm": "model", "checkpoint_enabled": True,
    })

    def save(state, ticker, path):
        assert state["market_report"] == "saved analyst work"
        assert state["trader_investment_plan"] == "saved trade"
        fake.calls.append(("save",))
        if save_fails:
            raise OSError("disk unavailable")
        return path / "complete_report.md"

    monkeypatch.setattr(m, "save_report_to_disk", save)
    m.run_analysis(checkpoint=True, selections={
        "ticker": "NVDA", "analysis_date": "2026-01-10", "asset_type": "stock",
        "analysts": [AnalystType.MARKET],
    }, post_save=True, post_display=False)
    assert fake.calls == [("begin",), ("end",), ("save",)] + (
        [] if save_fails else [("clear_checkpoint",)]
    )
