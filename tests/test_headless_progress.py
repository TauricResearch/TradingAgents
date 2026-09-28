"""Native dashboard integration, stream separation, and plain observer regressions."""

import json
import sys
from copy import deepcopy
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rich.console import Console
from typer.testing import CliRunner

import cli.headless as headless
import cli.main as main
import cli.progress as progress_module
import cli.run as native
from cli.progress import AnalysisProgress, analysis_progress, resolve_progress_mode
from tests.native_cli_helpers import RecordingGraph
from tradingagents.graph.propagation import Propagator


class Terminal(StringIO):

    def __init__(self, terminal=True):
        super().__init__()
        self.terminal = terminal

    def isatty(self):
        return self.terminal


@pytest.mark.parametrize("requested,json_output,out_tty,err_tty,term,expected", [
    (None, False, True, True, "xterm", "live"),
    (None, True, True, True, "xterm", "off"),
    (None, False, False, True, "xterm", "off"),
    (None, False, True, False, "xterm", "off"),
    (None, False, False, False, "xterm", "off"),
    (None, False, True, True, "dumb", "off"),
    (False, False, True, True, "xterm", "off"),
    (False, True, True, True, "xterm", "off"),
    (True, True, False, True, "xterm", "live"),
    (True, False, False, True, "xterm", "live"),
    (True, False, True, False, "xterm", "plain"),
    (True, True, False, False, "xterm", "plain"),
    (True, False, True, True, "dumb", "plain"),
])
def test_terminal_policy(requested, json_output, out_tty, err_tty, term, expected, monkeypatch):
    monkeypatch.setenv("TERM", term)
    assert resolve_progress_mode(requested, json_output, stdout=Terminal(out_tty), stderr=Terminal(err_tty)) == expected


def test_streams_without_isatty_are_not_terminals(monkeypatch):
    monkeypatch.setenv("TERM", "xterm")
    assert resolve_progress_mode(None, False, stdout=object(), stderr=object()) == "off"


@pytest.fixture
def observer():
    return AnalysisProgress("NVDA", "2026-09-28", ["market", "news"], console=Console(file=StringIO(), width=120, height=40))


def start_node(p, node, state=None, parent=None):
    if p._root is None:
        p.on_chain_start(None, {}, run_id="root", name="LangGraph")
    run_id = uuid4()
    p.on_chain_start(None, state or {}, run_id=run_id, parent_run_id=parent or "root",
                     metadata={"langgraph_node": node}, name=node)
    return run_id


def test_node_start_and_finish_and_nested_callbacks(observer):
    run_id = start_node(observer, "Market Analyst")
    assert observer.agents["Market Analyst"].status == "running"
    nested = start_node(observer, "Market Analyst", parent=run_id)
    observer.on_chain_end({}, run_id=nested)
    assert observer.agents["Market Analyst"].turns == 1
    assert observer.agents["Market Analyst"].status == "running"
    observer.on_chain_end({"market_report": "report"}, run_id=run_id)
    assert observer.agents["Market Analyst"].status == "completed"
    assert observer.reports == {"market_report"}
    assert observer.agents["News Analyst"].status == "pending"
    assert "Fundamentals Analyst" not in observer.agents


def test_tool_loop_does_not_finish_analyst_prematurely(observer):
    run_id = start_node(observer, "Market Analyst")
    observer.on_chain_end({"messages": [SimpleNamespace(tool_calls=[{"name": "get_stock_data"}])]}, run_id=run_id)
    assert observer.agents["Market Analyst"].status == "waiting"
    tools_id = start_node(observer, "tools_market")
    observer.on_tool_start({"name": "get_stock_data"}, "SECRET ARGUMENTS")
    assert observer.phase == "Fetching data: Market Analyst"
    observer.on_chain_end({}, run_id=tools_id)
    run_id = start_node(observer, "Market Analyst")
    observer.on_chain_end({"market_report": "finished"}, run_id=run_id)
    assert observer.agents["Market Analyst"].turns == 2
    assert observer.agents["Market Analyst"].status == "completed"
    assert observer.get_stats()["tool_calls"] == 1
    assert "SECRET" not in " ".join(observer.activity)


@pytest.mark.parametrize("members,manager", [
    (("Bull Researcher", "Bear Researcher"), "Research Manager"),
    (("Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"), "Portfolio Manager"),
])
def test_repeated_debate_turns_wait_until_judging(observer, members, manager):
    for _ in range(3):
        for name in members:
            run_id = start_node(observer, name)
            observer.on_chain_end({}, run_id=run_id)
            assert observer.agents[name].status == "waiting"
    start_node(observer, manager)
    for name in members:
        assert observer.agents[name].turns == 3
        assert observer.agents[name].status == "completed"
    assert observer.agents[manager].status == "running"


def test_checkpoint_node_input_restores_progress_without_reexecution(observer):
    state = {"market_report": "existing", "investment_plan": "plan",
             "investment_debate_state": {"bull_history": "bull", "bear_history": "bear", "judge_decision": "plan"}}
    original = deepcopy(state)
    start_node(observer, "Trader", state)
    assert observer.agents["Market Analyst"].status == "completed"
    assert observer.agents["Market Analyst"].turns == 0
    assert observer.agents["Bull Researcher"].status == "completed"
    assert observer.agents["Research Manager"].status == "completed"
    assert observer.agents["Trader"].status == "running"
    assert state == original


def test_failed_nested_attempt_does_not_fail_agent(observer):
    run_id = start_node(observer, "Trader")
    observer.on_llm_error(ValueError("secret response"))
    observer.on_chain_error(ValueError("secret"), run_id=uuid4())
    assert observer.agents["Trader"].status == "running"
    observer.on_chain_end({"trader_investment_plan": "valid fallback"}, run_id=run_id)
    assert observer.agents["Trader"].status == "completed"
    assert "secret" not in " ".join(observer.activity)


def test_node_failure_does_not_mark_unrun_agents_completed(observer):
    run_id = start_node(observer, "News Analyst")
    observer.on_chain_error(ValueError("secret"), run_id=run_id)
    observer.fail(ValueError("secret"))
    assert observer.agents["News Analyst"].status == "error"
    assert observer.agents["Trader"].status == "pending"
    assert observer.phase == "Failed"


def test_tool_node_failure_marks_owning_agent(observer):
    run_id = start_node(observer, "tools_market")
    observer.on_chain_error(ValueError("failed tool"), run_id=run_id)
    assert observer.agents["Market Analyst"].status == "error"


def test_elapsed_time_and_agent_timing_refresh_without_new_events(observer, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(progress_module, "monotonic", lambda: clock[0])
    observer.started = clock[0]
    start_node(observer, "Trader")
    clock[0] = 75.0
    observer.console.print(observer.render())
    text = observer.console.file.getvalue()
    assert "Elapsed 01:05" in text and "65s" in text
    assert "Trader" in text and "running" in text


def test_compact_display_keeps_stage_visible(observer):
    observer.console = Console(file=StringIO(), width=60, height=12)
    start_node(observer, "Trader")
    observer.console.print(observer.render())
    assert "Current: Trader" in observer.console.file.getvalue()


def test_instances_do_not_share_status_or_counts(observer):
    other = AnalysisProgress("AAPL", "2026-09-28", ["social"], console=observer.console)
    start_node(observer, "Trader")
    observer.on_chat_model_start({}, [])
    assert other.agents["Trader"].status == "pending"
    assert other.get_stats()["llm_calls"] == 0
    assert not other.activity


def test_propagator_observers_and_explicit_override():
    observer = object()
    supplied = [observer]
    p = Propagator(max_recur_limit=123, callbacks=supplied)
    supplied.clear()
    assert p.get_graph_args()["config"] == {"recursion_limit": 123, "callbacks": [observer]}
    assert p.get_graph_args([])["config"] == {"recursion_limit": 123}
    assert p.get_graph_args(["explicit"])["config"]["callbacks"] == ["explicit"]
    assert Propagator().get_graph_args() == {"stream_mode": "values", "config": {"recursion_limit": 100}}


@pytest.mark.parametrize("error", [ValueError("failure"), KeyboardInterrupt()])
def test_live_cleanup_on_failure_or_interrupt(monkeypatch, error):
    stream, stdout = Terminal(), StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    monkeypatch.setattr(sys, "stdout", stdout)
    with pytest.raises(type(error)), analysis_progress("live", "NVDA", "2026-09-28", ["market"]) as p:
        start_node(p, "Market Analyst")
        raise error
    assert p.agents["Market Analyst"].status == "error"
    assert p.phase in {"Failed", "Interrupted"}
    assert sys.stderr is stream and stdout.getvalue() == ""
    assert "\x1b[?25h" in stream.getvalue()


def test_off_mode_never_constructs_a_display(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("created display in off mode")
    monkeypatch.setattr(progress_module, "Console", forbidden)
    with analysis_progress("off", "NVDA", "2026-09-28", ["market"]) as p:
        assert p is None


@pytest.fixture
def fake_graph(monkeypatch, tmp_path):
    from tradingagents.default_config import DEFAULT_CONFIG
    config = deepcopy(DEFAULT_CONFIG)
    config.update(results_dir=str(tmp_path / "results"), llm_provider="openai",
                  quick_think_llm="gpt-4.1-mini", deep_think_llm="gpt-4.1")
    monkeypatch.setattr(main, "DEFAULT_CONFIG", config)
    monkeypatch.setattr(headless, "get_current_date", lambda: "2026-09-28")
    monkeypatch.setattr(native, "get_current_date", lambda: "2026-09-28")
    calls = []

    def create(selected, config, callbacks=None):
        graph = RecordingGraph(selected, config, callbacks)
        calls.append(graph)
        return graph
    monkeypatch.setattr(headless, "_create_graph", create)
    monkeypatch.setattr(native, "get_user_selections", lambda: pytest.fail("wizard entered"))
    return calls


@pytest.mark.parametrize("flags,observed", [([], False), (["--no-progress"], False),
    (["--progress"], True), (["--json"], False), (["--json", "--progress"], True)])
def test_cli_progress_flags_and_json_stream_separation(fake_graph, flags, observed):
    result = CliRunner().invoke(main.app, ["analyze", "NVDA", *flags])
    assert result.exit_code == 0, result.output
    # The native StatsCallbackHandler is always wired, even with no display.
    assert any(isinstance(cb, AnalysisProgress) for cb in fake_graph[0].observed) is observed
    if observed:
        assert "Market Analyst: running" in result.stderr
        assert "Completed; reports saved" in result.stderr
        assert "\x1b" not in result.stderr
    else:
        assert "Preparing analysis" not in result.stderr
    if "--json" in flags:
        assert json.loads(result.stdout)["decision"] == "Hold"
        assert "Market Analyst: running" not in result.stdout
    assert "private-tool-input" not in result.output


def test_cli_selects_auto_mode_before_redirect_stdout(fake_graph, monkeypatch):
    def resolve(requested, json_output):
        assert sys.stdout is not sys.stderr
        return "plain"
    monkeypatch.setattr(main, "resolve_progress_mode", resolve)
    assert CliRunner().invoke(main.app, ["analyze", "NVDA"]).exit_code == 0
    assert fake_graph[0].observed


def test_save_failure_is_not_shown_as_completed(fake_graph, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(native, "write_report_tree", fail)
    result = CliRunner().invoke(main.app, ["analyze", "NVDA", "--json", "--progress"])
    assert result.exit_code == 1
    assert "Saving reports" in result.stderr and "Failed" in result.stderr
    assert "Completed; reports saved" not in result.stderr
    assert not result.stdout.strip()


def test_callbacks_receive_actual_langgraph_nodes(observer):
    """Verify callback metadata against real LangGraph when installed."""
    graph_module = pytest.importorskip("langgraph.graph")
    from typing_extensions import TypedDict

    class State(TypedDict):
        market_report: str

    def market(state):
        assert observer.agents["Market Analyst"].status == "running"
        return {"market_report": "report"}
    workflow = graph_module.StateGraph(State)
    workflow.add_node("Market Analyst", market)
    workflow.add_edge(graph_module.START, "Market Analyst")
    workflow.add_edge("Market Analyst", graph_module.END)
    graph = workflow.compile()
    result = graph.invoke({"market_report": ""}, **Propagator(callbacks=[observer]).get_graph_args())
    assert result["market_report"] == "report"
    assert observer.agents["Market Analyst"].status == "completed"
    assert observer.agents["Market Analyst"].turns == 1


def test_token_counts_and_retry_attempts_use_existing_stats_handler(observer):
    from langchain_core.messages import AIMessage
    observer.on_chat_model_start({}, [])
    observer.on_llm_error(ValueError("retryable"))
    observer.on_chat_model_start({}, [])
    message = AIMessage(content="result", usage_metadata={"input_tokens": 120, "output_tokens": 40, "total_tokens": 160})
    observer.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(message=message)]]))
    assert observer.get_stats() == {"llm_calls": 2, "tool_calls": 0, "tokens_in": 120, "tokens_out": 40}


def test_json_stays_clean_with_native_live_renderer(fake_graph, monkeypatch):
    monkeypatch.setattr(main, "resolve_progress_mode", lambda *args: "live")
    original = native.update_display
    rendered = []

    def render(*args, **kwargs):
        rendered.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(native, "update_display", render)
    result = CliRunner().invoke(main.app, ["analyze", "NVDA", "--json", "--progress"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["decision"] == "Hold"
    assert rendered  # Reuses the interactive renderer, not a separate status panel.


def test_graph_setup_failure_closes_progress_without_success_json(fake_graph, monkeypatch):
    def fail(*args):
        raise ValueError("missing API key")
    monkeypatch.setattr(headless, "_create_graph", fail)
    result = CliRunner().invoke(main.app, ["analyze", "NVDA", "--json", "--progress"])
    assert result.exit_code == 1
    assert "Preparing analysis" in result.stderr and "Failed" in result.stderr
    assert "Completed; reports saved" not in result.stderr
    assert not result.stdout.strip()


def test_help_exposes_progress_flags():
    result = CliRunner().invoke(main.app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--progress" in result.output and "--no-progress" in result.output


def test_live_redirects_noisy_tools_to_stderr_and_restores_streams(monkeypatch):
    stderr, stdout = Terminal(), StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(sys, "stdout", stdout)
    with analysis_progress("live", "NVDA", "2026-09-28", ["market"]) as p:
        print("tool diagnostic")
        p.complete()
    assert sys.stdout is stdout and sys.stderr is stderr
    assert not stdout.getvalue()
    assert "tool diagnostic" in stderr.getvalue()
