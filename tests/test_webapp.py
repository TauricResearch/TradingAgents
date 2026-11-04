"""The web console: request checks, the option endpoints, and one run end to end.

The run test swaps in a fake graph, so it exercises the web layer's own work —
config assembly, the live buffer, the snapshot the page polls, the report links
— without calling a model.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from webapp import service
from webapp.app import create_app
from webapp.service import RunManager, RunOptions, RunRequestError


@pytest.fixture
def client():
    return TestClient(create_app(RunManager()))


def wait_for(run: service.Run, timeout: float = 10.0) -> service.Run:
    """Wait for a run's thread to finish, failing the test rather than hanging."""
    deadline = time.time() + timeout
    while run.status == "running" and time.time() < deadline:
        time.sleep(0.02)
    assert run.status != "running", "the run did not finish"
    return run


# ------------------------------------------------------------------ requests --


@pytest.mark.unit
class TestRunOptions:
    def test_a_ticker_is_canonicalised_and_its_asset_type_detected(self):
        selections = RunOptions(ticker="btcusd", analysis_date="2026-09-23",
                                analysts=["market"]).resolved()
        assert selections["ticker"] == "BTC-USD"
        assert selections["asset_type"] == "crypto"

    def test_analysts_are_checked_against_the_asset(self):
        with pytest.raises(RunRequestError, match="crypto"):
            RunOptions(ticker="BTC-USD", analysis_date="2026-09-23",
                       analysts=["fundamentals"]).resolved()

    def test_a_bad_ticker_a_date_and_depth_are_refused(self):
        with pytest.raises(RunRequestError, match="ticker"):
            RunOptions(ticker="  ", analysis_date="2026-09-23", analysts=["market"]).resolved()
        with pytest.raises(RunRequestError, match="future"):
            RunOptions(ticker="NVDA", analysis_date="2999-01-01", analysts=["market"]).resolved()
        with pytest.raises(RunRequestError, match="depth"):
            RunOptions(ticker="NVDA", analysis_date="2026-09-23", analysts=["market"],
                       research_depth=2).resolved()

    def test_an_empty_analyst_choice_and_a_malformed_portfolio_are_refused(self):
        with pytest.raises(RunRequestError, match="analyst"):
            RunOptions(ticker="NVDA", analysis_date="2026-09-23", analysts=[]).resolved()
        with pytest.raises(RunRequestError, match="portfolio"):
            RunOptions(ticker="NVDA", analysis_date="2026-09-23", analysts=["market"],
                       portfolio={"cash": "not a number"}).resolved()

    def test_defaults_come_from_the_shared_config(self):
        selections = RunOptions(ticker="NVDA", analysis_date="2026-09-23",
                                analysts=["market", "news"]).resolved()
        assert selections["save"] is True
        assert [a.value for a in selections["analysts"]] == ["market", "news"]
        assert selections["output_language"]


# ------------------------------------------------------------------- the API --


@pytest.mark.unit
class TestApi:
    def test_health_and_options_describe_the_same_providers_the_cli_offers(self, client):
        assert client.get("/api/health").json()["status"] == "ok"
        options = client.get("/api/options").json()
        assert {p["key"] for p in options["providers"]} >= {"openai", "anthropic", "ollama"}
        assert [a["key"] for a in options["analysts"]] == ["market", "social", "news", "fundamentals"]
        assert {d["value"] for d in options["depths"]} == {1, 3, 5}

    def test_models_follow_the_shared_catalog(self, client):
        body = client.get("/api/models/deepseek").json()
        assert body["quick"] and body["deep"]
        assert any(m["value"] == "custom" for m in body["quick"])

    def test_detect_reports_the_canonical_symbol_and_the_allowed_analysts(self, client):
        body = client.get("/api/detect", params={"ticker": "0700.hk"}).json()
        assert body["canonical"] == "0700.HK"
        assert body["asset_type"] == "stock"
        crypto = client.get("/api/detect", params={"ticker": "BTC-USD"}).json()
        assert "fundamentals" not in crypto["available_analysts"]
        assert client.get("/api/detect", params={"ticker": "NV DA"}).json()["valid"] is False

    def test_a_bad_request_is_422_with_the_reason(self, client):
        response = client.post("/api/runs", json={"ticker": "NVDA", "analysts": ["market"],
                                                  "analysis_date": "2999-01-01"})
        assert response.status_code == 422
        assert "future" in response.json()["detail"]

    def test_an_unknown_run_is_404(self, client):
        assert client.get("/api/runs/nope").status_code == 404
        assert client.post("/api/runs/nope/cancel").status_code == 404

    def test_the_page_and_its_assets_are_served(self, client):
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/styles.css").status_code == 200

    def test_a_non_local_host_header_is_refused(self, client):
        response = client.get("/api/health", headers={"host": "example.com"})
        assert response.status_code == 403


# ----------------------------------------------------------------- the run --


class _FakePropagator:
    def get_graph_args(self, callbacks=None):
        return {"config": {}}


class _FakeGraph:
    """A graph that streams two reports and a decision, shaped like the real one."""

    last_instance: _FakeGraph | None = None

    def __init__(self, selected_analysts, config=None, debug=False, callbacks=None):
        self.selected_analysts = list(selected_analysts)
        self.config = config
        self.callbacks = callbacks or []
        self.propagator = _FakePropagator()
        self._resuming = False
        self.saved: dict = {}
        _FakeGraph.last_instance = self

    def create_run_state(self, ticker, trade_date, asset_type="stock", portfolio=None):
        return {"company_of_interest": ticker, "trade_date": trade_date, "messages": []}

    def begin_checkpoint(self, *args, **kwargs):
        return None

    def checkpoint_input(self, init_state):
        return init_state

    def end_checkpoint(self):
        return None

    def stream_run(self, graph_input, **args):
        yield [HumanMessage(content="Continue")], None
        yield [AIMessage(content="Market looks strong on volume.")], {"market_report": "## Market\nStrong."}
        yield [AIMessage(content="News is quiet.")], {"news_report": "## News\nQuiet."}
        yield [AIMessage(content="Decision made.")], {
            "investment_debate_state": {"bull_history": "Bull case.", "bear_history": "Bear case."},
            "investment_plan": "Research says buy.",
            "trader_investment_plan": "Trader plan.",
            "risk_debate_state": {
                "aggressive_history": "Go big.",
                "conservative_history": "Be careful.",
                "neutral_history": "Balance.",
            },
            "final_trade_decision": "- **Rating**: Buy\n\nAdd on weakness.",
        }

    def record_decision(self, ticker, trade_date, final_state):
        self.saved["decision"] = (ticker, trade_date)

    def clear_checkpoint_on_success(self, *args, **kwargs):
        return None

    def save_reports(self, final_state, ticker, save_path=None, html=True):
        from pathlib import Path

        self.saved["reports"] = (ticker, html)
        directory = Path(self.config["results_dir"]) / "reports" / f"{ticker}_stub"
        directory.mkdir(parents=True, exist_ok=True)
        page = directory / "complete_report.html"
        page.write_text("<html>report</html>", encoding="utf-8")
        (directory / "complete_report.md").write_text("# report", encoding="utf-8")
        return page


@pytest.mark.unit
def test_a_run_reaches_the_page_and_writes_its_report(monkeypatch):
    monkeypatch.setattr(service, "TradingAgentsGraph", _FakeGraph)

    manager = RunManager()
    run = manager.start(RunOptions(
        ticker="NVDA", analysis_date="2026-09-23", analysts=["market", "news"],
        llm_provider="openai", quick_think_llm="gpt-6-luna", deep_think_llm="gpt-6-sol",
        save=True, html=True,
    ))
    wait_for(run)

    assert run.status == "completed", run.error
    assert run.rating == "Buy"
    assert run.report_html and run.report_html.endswith("complete_report.html")

    snapshot = run.snapshot()
    assert snapshot["progress"]["agents_completed"] == snapshot["progress"]["agents_total"]
    assert snapshot["report_sections"]["market_report"]
    assert snapshot["report_sections"]["final_trade_decision"].endswith("Add on weakness.")
    assert any("Market looks strong" in m["content"] for m in snapshot["messages"])
    assert snapshot["report_available"] is True

    graph = _FakeGraph.last_instance
    assert graph.selected_analysts == ["market", "news"]
    assert graph.saved["decision"] == ("NVDA", "2026-09-23")
    assert graph.saved["reports"] == ("NVDA", True)
    assert graph.config["llm_provider"] == "openai"


@pytest.mark.unit
def test_a_run_that_raises_is_reported_as_failed(monkeypatch):
    class ExplodingGraph(_FakeGraph):
        def stream_run(self, graph_input, **args):
            raise RuntimeError("vendor unreachable")
            yield  # pragma: no cover - makes this a generator like the real one

    monkeypatch.setattr(service, "TradingAgentsGraph", ExplodingGraph)
    manager = RunManager()
    run = manager.start(RunOptions(ticker="NVDA", analysis_date="2026-09-23", analysts=["market"]))
    wait_for(run)

    assert run.status == "failed"
    assert "vendor unreachable" in run.error


@pytest.mark.unit
def test_cancelling_a_finished_run_is_refused_and_an_active_one_is_flagged(monkeypatch):
    monkeypatch.setattr(service, "TradingAgentsGraph", _FakeGraph)
    manager = RunManager()
    run = manager.start(RunOptions(ticker="NVDA", analysis_date="2026-09-23", analysts=["market"]))
    assert manager.cancel(run.id) is True
    wait_for(run)
    assert manager.cancel(run.id) is False


@pytest.mark.unit
def test_history_keeps_recent_runs_only(monkeypatch):
    monkeypatch.setattr(service, "TradingAgentsGraph", _FakeGraph)
    manager = RunManager(history=2)
    runs = [manager.start(RunOptions(ticker="NVDA", analysis_date="2026-09-23", analysts=["market"]))
            for _ in range(3)]
    for run in runs:
        wait_for(run)
    manager.start(RunOptions(ticker="NVDA", analysis_date="2026-09-23", analysts=["market"]))
    listed = manager.list()
    assert len(listed) <= 3
