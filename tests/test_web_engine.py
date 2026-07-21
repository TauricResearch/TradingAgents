"""AnalysisEngine scaffolding conformance: stream_mode override, async
checkpointer construction, post-phase order, incremental report writes,
run.json manifest."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from tradingagents.graph.propagation import Propagator
from tradingagents.web.engine import AnalysisEngine, build_run_config

pytestmark = pytest.mark.unit


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeGraph:
    """Records the propagate() scaffolding calls the web engine must make."""

    def __init__(self, selected_analysts, config=None, callbacks=None, chunks=None):
        self.config = config
        self.callbacks = callbacks
        self.calls = []
        self.propagator = Propagator()
        self.memory_log = MagicMock()
        self.memory_log.get_past_context.return_value = ""
        self.ticker = None
        self.curr_state = None
        self._chunks = chunks if chunks is not None else [
            ("updates", {"Market Analyst": {"market_report": "# market"}}),
            ("updates", {"Portfolio Manager": {
                "risk_debate_state": {"judge_decision": "buy it"},
                "final_trade_decision": "FINAL: BUY",
            }}),
        ]
        self.stream_args = None
        self.workflow = MagicMock()
        self.workflow.compile.side_effect = self._compile
        self.graph = self._compile()

    def _compile(self, checkpointer=None):
        self.calls.append(("compile", checkpointer))
        compiled = MagicMock()
        compiled.astream = self._astream
        compiled.checkpointer = checkpointer
        return compiled

    def _astream(self, init_state, **kwargs):
        self.stream_args = kwargs
        self.calls.append(("astream", init_state))

        async def gen():
            for item in self._chunks:
                yield item

        return gen()

    def _resolve_pending_entries(self, ticker):
        self.calls.append(("resolve_pending", ticker))

    def resolve_instrument_context(self, ticker, asset_type):
        self.calls.append(("instrument", ticker, asset_type))
        return f"context for {ticker}"

    def _run_signature(self, asset_type):
        return f"sig:{asset_type}"

    def _log_state(self, date, final_state):
        self.calls.append(("log_state", date))

    def process_signal(self, decision):
        self.calls.append(("process_signal", decision))
        return "BUY"


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path / "results"))
    monkeypatch.setitem(DEFAULT_CONFIG, "data_cache_dir", str(tmp_path / "cache"))
    return tmp_path / "results"


def _params(**overrides):
    params = {
        "run_id": "run-1",
        "ticker": "AAPL",
        "date": "2026-07-01",
        "asset_type": "stock",
        "analysts": ["market"],
        "research_depth": 1,
        "provider": "openai",
        "deep_think_llm": "gpt-5.5",
        "quick_think_llm": "gpt-5.4-mini",
    }
    params.update(overrides)
    return params


def _run(engine, params):
    events = []

    def emit(event_type, data):
        events.append((event_type, data))

    result = asyncio.run(engine(params, emit))
    return result, events


def test_stream_mode_overrides_propagator_default(results_dir):
    graphs = []

    def factory(analysts, config=None, callbacks=None):
        graph = FakeGraph(analysts, config=config, callbacks=callbacks)
        graphs.append(graph)
        return graph

    engine = AnalysisEngine(graph_factory=factory)
    result, events = _run(engine, _params())

    graph = graphs[0]
    # get_graph_args hardcodes "values"; the web path must stream updates.
    assert graph.stream_args["stream_mode"] == ["updates", "custom"]
    assert result["decision"] == "BUY"
    memory = graph.memory_log
    memory.store_decision.assert_called_once()
    assert memory.store_decision.call_args.kwargs["final_trade_decision"] == "FINAL: BUY"


def test_post_phase_order_matches_propagate(results_dir, monkeypatch):
    order = []
    graphs = []

    def factory(analysts, config=None, callbacks=None):
        graph = FakeGraph(analysts, config=config, callbacks=callbacks)
        graph.memory_log.store_decision.side_effect = (
            lambda **kw: order.append("store_decision")
        )
        original_log = graph._log_state
        original_signal = graph.process_signal

        def log_state(date, state):
            order.append("log_state")
            return original_log(date, state)

        def process_signal(decision):
            order.append("process_signal")
            return original_signal(decision)

        graph._log_state = log_state
        graph.process_signal = process_signal
        graphs.append(graph)
        return graph

    monkeypatch.setattr(
        "tradingagents.web.engine.clear_checkpoint",
        lambda *args, **kwargs: order.append("clear_checkpoint"),
    )

    @asynccontextmanager
    async def fake_checkpointer(data_dir, ticker):
        order.append("checkpointer_open")
        yield MagicMock()

    engine = AnalysisEngine(graph_factory=factory, checkpointer_factory=fake_checkpointer)
    _run(engine, _params(checkpoint_enabled=True))

    assert order == [
        "checkpointer_open", "log_state", "store_decision",
        "clear_checkpoint", "process_signal",
    ]


def test_checkpoint_run_compiles_with_async_saver_and_thread_id(results_dir):
    graphs = []
    saver = MagicMock(name="async_saver")

    @asynccontextmanager
    async def fake_checkpointer(data_dir, ticker):
        yield saver

    def factory(analysts, config=None, callbacks=None):
        graph = FakeGraph(analysts, config=config, callbacks=callbacks)
        graphs.append(graph)
        return graph

    engine = AnalysisEngine(graph_factory=factory, checkpointer_factory=fake_checkpointer)
    _run(engine, _params(checkpoint_enabled=True))

    graph = graphs[0]
    compile_calls = [c for c in graph.calls if c[0] == "compile"]
    # initial compile (None) -> checkpointer compile -> restore compile (None)
    assert [c[1] for c in compile_calls] == [None, saver, None]
    assert graph.stream_args["config"]["configurable"]["thread_id"]


def test_no_checkpoint_run_never_opens_checkpointer(results_dir):
    opened = []

    @asynccontextmanager
    async def fake_checkpointer(data_dir, ticker):
        opened.append(ticker)
        yield MagicMock()

    engine = AnalysisEngine(
        graph_factory=lambda *a, **k: FakeGraph(*a, **k),
        checkpointer_factory=fake_checkpointer,
    )
    _run(engine, _params())
    assert opened == []


def test_incremental_section_writes_and_manifest(results_dir):
    engine = AnalysisEngine(graph_factory=lambda *a, **k: FakeGraph(*a, **k))
    result, events = _run(engine, _params())

    run_dir = results_dir / "AAPL" / "2026-07-01"
    assert (run_dir / "reports" / "market_report.md").read_text(encoding="utf-8") == "# market"
    assert (run_dir / "reports" / "final_trade_decision.md").is_file()

    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "done"
    assert manifest["decision"] == "BUY"
    assert manifest["run_id"] == "run-1"
    assert manifest["provider"] == "openai"
    assert manifest["analysts"] == ["market"]
    assert manifest["duration_seconds"] is not None

    event_types = [etype for etype, _ in events]
    assert "report_section" in event_types
    assert "agent_status" in event_types
    assert "stats" in event_types


def test_failure_writes_failed_manifest(results_dir):
    class ExplodingGraph(FakeGraph):
        def _astream(self, init_state, **kwargs):
            async def gen():
                raise RuntimeError("provider down")
                yield  # pragma: no cover

            return gen()

    engine = AnalysisEngine(graph_factory=lambda *a, **k: ExplodingGraph(*a, **k))
    with pytest.raises(RuntimeError, match="provider down"):
        _run(engine, _params())

    manifest = json.loads(
        (results_dir / "AAPL" / "2026-07-01" / "run.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert "provider down" in manifest["error"]


def test_build_run_config_maps_depth_and_provider(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_MAX_RISK_ROUNDS", raising=False)
    config = build_run_config(_params(research_depth=3, provider="OpenAI"))
    assert config["max_debate_rounds"] == 3
    assert config["max_risk_discuss_rounds"] == 3
    assert config["llm_provider"] == "openai"
    assert config["backend_url"] == "https://api.openai.com/v1"


def test_build_run_config_env_rounds_win(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "7")
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setitem(DEFAULT_CONFIG, "max_debate_rounds", 7)
    config = build_run_config(_params(research_depth=1))
    assert config["max_debate_rounds"] == 7


def test_build_run_config_omitted_knobs_keep_env_defaults(monkeypatch):
    from tradingagents.default_config import DEFAULT_CONFIG

    # Simulates TRADINGAGENTS_OPENAI_REASONING_EFFORT supplying a base default.
    monkeypatch.setitem(DEFAULT_CONFIG, "openai_reasoning_effort", "high")
    config = build_run_config(_params())
    assert config["openai_reasoning_effort"] == "high"

    config = build_run_config(_params(openai_reasoning_effort="low"))
    assert config["openai_reasoning_effort"] == "low"


def test_build_run_config_sets_llm_timeout_default(monkeypatch):
    from tradingagents.default_config import DEFAULT_CONFIG

    config = build_run_config(_params())
    assert config["llm_timeout"] == 600.0

    monkeypatch.setitem(DEFAULT_CONFIG, "llm_timeout", 120)
    config = build_run_config(_params())
    assert config["llm_timeout"] == 120
