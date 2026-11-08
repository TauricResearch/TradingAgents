"""The /decide server-side deadline guard (fork audit R3, 2026-11-09).

Before this, a decision that outlived the caller's 600s HTTP timeout kept
executing -- and billing -- server-side, because uvicorn does not cancel a
sync handler on client disconnect (2026-09-10: six consecutive timeouts,
each still spending). The guard wraps the graph's two shared tier LLMs so
any invoke past the deadline raises DeadlineExceeded *before* the billed
call, and scripts/service.py maps that to a definitive 504.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from tradingagents.llm_clients.deadline import DeadlineExceeded, DeadlineGuardedRunnable


class _ScriptedChat(BaseChatModel):
    """Minimal chat model for the graph-wiring tests -- the analysts call
    bind_tools()/with_structured_output() before the first invoke, so a
    bare RunnableLambda won't do (same reason test_graph_end_to_end.py has
    ScriptedModel). The deadline tests never need a real answer from it."""

    @property
    def _llm_type(self) -> str:
        return "scripted-deadline-test"

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        raise NotImplementedError

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content="Report.\n\n**Rating**: Overweight\n\nFINAL TRANSACTION PROPOSAL: **BUY**"))])


def _load_script(name: str, filename: str):
    """scripts/ isn't a package -- load by path, same pattern
    test_decide_service.py uses."""
    path = Path(__file__).parent.parent / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestDeadlineGuardedRunnable:
    def test_invoke_before_the_deadline_delegates(self):
        guard = DeadlineGuardedRunnable(RunnableLambda(lambda x: f"echo:{x}"),
                                        time.monotonic() + 60, "test")
        assert guard.invoke("hi") == "echo:hi"

    def test_invoke_after_the_deadline_raises_and_the_inner_never_runs(self):
        calls = []
        guard = DeadlineGuardedRunnable(RunnableLambda(lambda x: calls.append(x) or "x"),
                                        time.monotonic() - 1, "quick")
        with pytest.raises(DeadlineExceeded, match="quick"):
            guard.invoke("hi")
        assert calls == []

    def test_a_zero_deadline_is_already_expired(self):
        guard = DeadlineGuardedRunnable(RunnableLambda(lambda x: "x"), time.monotonic() + 0.0)
        with pytest.raises(DeadlineExceeded):
            guard.invoke("hi")

    def test_bound_tools_stay_guarded(self):
        class Tooly:
            def bind_tools(self, tools, **kw):
                return RunnableLambda(lambda x: f"bound:{x}")

        guard = DeadlineGuardedRunnable(Tooly(), time.monotonic() - 1)
        bound = guard.bind_tools(["t"])
        assert isinstance(bound, DeadlineGuardedRunnable)
        with pytest.raises(DeadlineExceeded):
            bound.invoke("hi")

    def test_structured_output_stays_guarded(self):
        class Structured:
            def with_structured_output(self, schema, **kw):
                return RunnableLambda(lambda x: {"ok": True})

        guard = DeadlineGuardedRunnable(Structured(), time.monotonic() - 1)
        with pytest.raises(DeadlineExceeded):
            guard.with_structured_output(dict).invoke("hi")

    def test_unknown_attributes_pass_through(self):
        inner = RunnableLambda(lambda x: "x")
        inner.model_name = "claude-haiku-4-5-20251001"
        guard = DeadlineGuardedRunnable(inner, time.monotonic() + 60)
        assert guard.model_name == "claude-haiku-4-5-20251001"

    def test_works_in_a_prompt_chain(self):
        """The analysts' wrap-up turn is `(prompt | llm).invoke(...)` -- the
        guard must be a well-behaved Runnable in that position."""
        prompt = ChatPromptTemplate.from_messages([("human", "{question}")])
        chain = prompt | DeadlineGuardedRunnable(RunnableLambda(lambda pv: f"saw:{pv.messages[-1].content}"),
                                                 time.monotonic() + 60)
        assert chain.invoke({"question": "price?"}) == "saw:price?"


@pytest.mark.unit
class TestGraphWiring:
    """TradingAgentsGraph(deadline_sec=...) must wrap BOTH tier LLMs before
    GraphSetup and Reflector receive them -- one interception point, whole
    graph covered. Vendor/network points are stubbed exactly like
    test_graph_end_to_end.py's offline fixture."""

    def _graph(self, tmp_path, monkeypatch, deadline_sec):
        import pandas as pd

        from tradingagents.agents import context
        from tradingagents.agents.analysts import sentiment_analyst
        from tradingagents.dataflows import router
        from tradingagents.dataflows.vendors.yahoo import market as yahoo_market, snapshot
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph import trading_graph

        for method, vendors in router.VENDOR_METHODS.items():
            for vendor in vendors:
                monkeypatch.setitem(vendors, vendor, lambda *a, _m=method, **k: f"{_m} data")
        prices = pd.DataFrame({
            "Date": pd.bdate_range(end="2026-01-09", periods=60),
            "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1_000_000,
        })
        monkeypatch.setattr(snapshot, "load_ohlcv", lambda *a, **k: prices.copy())
        monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages", lambda *a, **k: "no posts")
        monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts", lambda *a, **k: "no posts")
        monkeypatch.setattr(yahoo_market.yf, "Ticker",
                            lambda s: type("T", (), {"info": {"longName": "NVIDIA"}})())
        context._identity.cache_clear()

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg.update(results_dir=str(tmp_path / "results"), data_cache_dir=str(tmp_path / "cache"),
                   memory_log_path=str(tmp_path / "log.md"))
        fake_llm = _ScriptedChat()
        client = type("C", (), {"get_llm": lambda self: fake_llm})()
        monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: client)
        return trading_graph.TradingAgentsGraph(config=cfg, debug=False, deadline_sec=deadline_sec)

    def test_both_tier_llms_are_wrapped(self, tmp_path, monkeypatch):
        graph = self._graph(tmp_path, monkeypatch, deadline_sec=3600)
        assert isinstance(graph.deep_thinking_llm, DeadlineGuardedRunnable)
        assert isinstance(graph.quick_thinking_llm, DeadlineGuardedRunnable)

    def test_no_deadline_leaves_the_llms_unwrapped(self, tmp_path, monkeypatch):
        graph = self._graph(tmp_path, monkeypatch, deadline_sec=None)
        assert not isinstance(graph.deep_thinking_llm, DeadlineGuardedRunnable)
        assert not isinstance(graph.quick_thinking_llm, DeadlineGuardedRunnable)

    def test_an_expired_deadline_aborts_the_run_before_any_billed_call(self, tmp_path, monkeypatch):
        """deadline_sec=0: every analyst's first LLM invoke raises inside its
        parallel branch, and the run must surface DeadlineExceeded -- this is
        the 2026-09-10 incident path, now stopped instead of billed."""
        graph = self._graph(tmp_path, monkeypatch, deadline_sec=0.0)
        with pytest.raises(DeadlineExceeded):
            graph.propagate("NVDA", "2026-01-09")


@pytest.mark.unit
class TestRunDecisionThreadsDeadline:
    def test_deadline_reaches_the_graph_constructor(self):
        decide = _load_script("tradingagents_decide_deadline_test", "decide.py")
        fake_final_state = {"final_trade_decision": "FINAL TRANSACTION PROPOSAL: **BUY**"}
        with patch.object(decide, "TradingAgentsGraph") as MockGraph:
            MockGraph.return_value.propagate.return_value = (fake_final_state, "Buy")
            decide.run_decision("WIPRO.NS", "2026-07-16", deadline_sec=570.0)
        assert MockGraph.call_args.kwargs["deadline_sec"] == 570.0

    def test_default_is_no_deadline(self):
        decide = _load_script("tradingagents_decide_deadline_test", "decide.py")
        fake_final_state = {"final_trade_decision": "FINAL TRANSACTION PROPOSAL: **BUY**"}
        with patch.object(decide, "TradingAgentsGraph") as MockGraph:
            MockGraph.return_value.propagate.return_value = (fake_final_state, "Buy")
            decide.run_decision("WIPRO.NS", "2026-07-16")
        assert MockGraph.call_args.kwargs["deadline_sec"] is None


@pytest.mark.unit
class TestServiceDeadline:
    """The endpoint maps DeadlineExceeded to a definitive 504 and always
    passes its configured deadline through to run_decision."""

    @pytest.fixture
    def service(self):
        return _load_script("tradingagents_service_deadline_test", "service.py")

    @pytest.fixture
    def client(self, service):
        from fastapi.testclient import TestClient
        return TestClient(service.app)

    @pytest.fixture(autouse=True)
    def _no_network(self, monkeypatch):
        """Same loopback-only override as test_decide_service.py (Windows
        Proactor self-pipe vs conftest's blanket guard)."""
        import socket

        real_connect = socket.socket.connect

        def loopback_only(sock, address, *args, **kwargs):
            host = address[0] if isinstance(address, tuple) else address
            if host not in ("127.0.0.1", "::1", "localhost"):
                raise OSError(f"test tried to reach the network: {address}")
            return real_connect(sock, address, *args, **kwargs)

        monkeypatch.setattr(socket.socket, "connect", loopback_only)

    def test_deadline_exceeded_maps_to_504_not_500(self, client, service):
        service._SERVICE_SECRET = "s"
        with patch.object(service, "run_decision",
                          side_effect=DeadlineExceeded("decision deadline passed 3.0s ago")):
            resp = client.post(
                "/decide", json={"ticker": "WIPRO.NS", "trade_date": "2026-07-16"},
                headers={"Authorization": "Bearer s"},
            )
        assert resp.status_code == 504
        assert "deadline" in resp.json()["detail"]

    def test_other_failures_still_map_to_500(self, client, service):
        service._SERVICE_SECRET = "s"
        with patch.object(service, "run_decision", side_effect=RuntimeError("provider down")):
            resp = client.post(
                "/decide", json={"ticker": "WIPRO.NS", "trade_date": "2026-07-16"},
                headers={"Authorization": "Bearer s"},
            )
        assert resp.status_code == 500

    def test_configured_deadline_is_passed_through(self, client, service):
        service._SERVICE_SECRET = "s"
        with patch.object(service, "run_decision", return_value={"rating": "Hold"}) as mock_run:
            client.post(
                "/decide", json={"ticker": "WIPRO.NS", "trade_date": "2026-07-16"},
                headers={"Authorization": "Bearer s"},
            )
        assert mock_run.call_args.kwargs["deadline_sec"] == service._DECIDE_DEADLINE_SEC
        # Just under the caller's DECIDE_TIMEOUT_SEC=600, so the server stops
        # (and answers 504) before the client would time out.
        assert 0 < service._DECIDE_DEADLINE_SEC < 600
