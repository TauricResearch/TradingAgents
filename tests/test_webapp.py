"""The web console: request checks, the option endpoints, and one run end to end.

The run test swaps in a fake graph, so it exercises the web layer's own work —
config assembly, the live buffer, the snapshot the page polls, the report links
— without calling a model.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from tradingagents.memory import TradingMemoryLog
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

    def test_languages_match_the_cli_menu_and_include_italian(self, client):
        from cli.prompts import OUTPUT_LANGUAGES

        options = client.get("/api/options").json()
        assert [(entry["label"], entry["value"]) for entry in options["languages"]] == OUTPUT_LANGUAGES
        assert {"label": "Italian (Italiano)", "value": "Italian"} in options["languages"]

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


# ------------------------------------------------------- the report markdown --


@pytest.mark.unit
class TestMarkdown:
    def test_common_markdown_becomes_formatted_html(self):
        from webapp.rendering import render_markdown

        html = render_markdown("**bold**, *em*, `code`\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |")
        assert "<strong>bold</strong>" in html
        assert "<em>em</em>" in html
        assert "<code>code</code>" in html
        assert "<li>one</li>" in html
        assert "<table>" in html and "<th>a</th>" in html
        assert 'class="table-wrap"' in html

    def test_raw_html_is_escaped_rather_than_executed(self):
        from webapp.rendering import render_markdown

        html = render_markdown("<script>alert('x')</script>\n\n<img src=x onerror=alert(1)>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<img" not in html

    def test_a_section_heading_sits_below_the_panel_heading(self):
        from webapp.rendering import render_markdown

        # The panel labels a section with the agent's name at h3, so the text's
        # own headings start below it.
        html = render_markdown("## Market Analysis\n\n### Key readings\n\nText.")
        assert "<h4>Market Analysis</h4>" in html
        assert "<h5>Key readings</h5>" in html
        assert "<h2>" not in html and "<h3>" not in html

    def test_empty_text_renders_nothing(self):
        from webapp.rendering import render_markdown

        assert render_markdown("") == ""
        assert render_markdown(None) == ""

    def test_the_same_text_is_rendered_once(self):
        from webapp.rendering import _render_cached, render_markdown

        _render_cached.cache_clear()
        render_markdown("## Cached\n\nBody.")
        render_markdown("## Cached\n\nBody.")
        assert _render_cached.cache_info().hits == 1


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

    def record_decision(self, ticker, trade_date, final_state, portfolio=None):
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
    # The page renders the report, so the same sections come pre-rendered too,
    # and only the ones with content.
    assert "<h4>Market</h4>" in snapshot["report_sections_html"]["market_report"]
    assert "<strong>Rating</strong>" in snapshot["report_sections_html"]["final_trade_decision"]
    assert set(snapshot["report_sections_html"]) == {
        key for key, value in snapshot["report_sections"].items() if value
    }
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


# ------------------------------------------------------------------ archive --

def _write_finished_report(root, folder, ticker, date, rating="Buy", html=True):
    """A reports/<TICKER>_<stamp>/ tree, as save_reports writes one."""
    directory = root / "reports" / folder
    (directory / "1_analysts").mkdir(parents=True)
    (directory / "5_portfolio").mkdir(parents=True)
    (directory / "complete_report.md").write_text(
        f"# Trading Analysis Report: {ticker}\n\n"
        f"- Analysis date: {date}\n"
        f"- Rating: {rating}\n\n"
        "## I. Analyst Team Reports\n\n### Market Analyst\nA strong quarter.\n",
        encoding="utf-8",
    )
    (directory / "1_analysts" / "market.md").write_text("## Market\nUptrend intact.", encoding="utf-8")
    (directory / "5_portfolio" / "decision.md").write_text("**Rating**: Buy", encoding="utf-8")
    if html:
        (directory / "complete_report.html").write_text("<html>report</html>", encoding="utf-8")
    return directory


def _write_run_folder(root, ticker, date, sections=("market_report.md", "final_trade_decision.md")):
    """A <TICKER>/<date>/reports/ folder, as a run writes one while it goes."""
    directory = root / ticker / date / "reports"
    directory.mkdir(parents=True)
    for name in sections:
        (directory / name).write_text("**Rating**: Hold\n\nKept as written.", encoding="utf-8")
    return directory.parent


@pytest.mark.unit
class TestArchive:
    def test_lists_a_finished_report_with_its_ticker_date_and_rating(self, tmp_path):
        _write_finished_report(tmp_path, "AAPL_20261104_124818", "AAPL", "2026-11-04", "Buy")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        reports = client.get("/api/archive").json()["reports"]

        assert len(reports) == 1
        entry = reports[0]
        assert entry["id"] == "reports/AAPL_20261104_124818"
        assert entry["ticker"] == "AAPL"
        assert entry["analysis_date"] == "2026-11-04"
        assert entry["rating"] == "Buy"
        assert entry["source"] == "report"
        assert entry["has_html"] is True
        assert "Market Analyst" in entry["section_titles"]

    def test_a_report_without_html_offers_no_html_link(self, tmp_path):
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-04", html=False)
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        assert client.get("/api/archive").json()["reports"][0]["has_html"] is False
        assert client.get("/api/archive/reports/AAPL_1/report").status_code == 404
        assert client.get("/api/archive/reports/AAPL_1/report.md").status_code == 200

    def test_the_markdown_report_can_be_downloaded_as_a_file(self, tmp_path):
        """The download button saves the report instead of opening a tab:
        ?download=1 serves it as an attachment with a named file."""
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-04")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        inline = client.get("/api/archive/reports/AAPL_1/report.md")
        assert inline.status_code == 200
        assert inline.headers["content-disposition"].startswith("inline")
        assert inline.headers["content-type"].startswith("text/markdown")

        downloaded = client.get("/api/archive/reports/AAPL_1/report.md?download=1")
        assert downloaded.status_code == 200
        disposition = downloaded.headers["content-disposition"]
        assert disposition.startswith("attachment")
        assert "complete_report.md" in disposition
        assert downloaded.text.startswith("# Trading Analysis Report")

    def test_an_unknown_rating_is_not_reported_as_a_tier(self, tmp_path):
        # A decision nobody could read is "REVIEW", which is not a position.
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-04", rating="REVIEW")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        assert client.get("/api/archive").json()["reports"][0]["rating"] is None

    def test_an_unfinished_run_is_listed_when_no_finished_report_covers_it(self, tmp_path):
        _write_run_folder(tmp_path, "BTC-USD", "2026-11-04")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        reports = client.get("/api/archive").json()["reports"]

        assert len(reports) == 1
        assert reports[0]["id"] == "BTC-USD/2026-11-04"
        assert reports[0]["source"] == "run"
        assert reports[0]["rating"] == "Hold"
        assert reports[0]["has_html"] is False
        # Its sections live one level down, under the run's own reports folder.
        sections = client.get("/api/archive/BTC-USD/2026-11-04/sections").json()["sections"]
        assert [s["title"] for s in sections] == ["Market Analyst", "Portfolio Manager"]

    def test_a_finished_report_hides_the_run_folder_it_covers(self, tmp_path):
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-04")
        _write_run_folder(tmp_path, "AAPL", "2026-11-04")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        entries = client.get("/api/archive").json()["reports"]

        assert [e["source"] for e in entries] == ["report"]

    def test_sections_come_back_rendered_as_safe_html(self, tmp_path):
        directory = _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-04")
        (directory / "1_analysts" / "market.md").write_text(
            "## Market\n\n<script>alert(1)</script>\n\n**bold**", encoding="utf-8"
        )
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        sections = client.get("/api/archive/reports/AAPL_1/sections").json()["sections"]

        market = next(s for s in sections if s["title"] == "Market Analyst")
        assert "<strong>bold</strong>" in market["html"]
        assert "<script>" not in market["html"]

    def test_no_report_is_served_from_outside_the_results_directory(self, tmp_path):
        root = tmp_path / "results"
        _write_finished_report(root, "AAPL_1", "AAPL", "2026-11-04")
        (tmp_path / "secret.md").write_text("private", encoding="utf-8")
        client = TestClient(create_app(RunManager(), results_dir=root))

        for bad in ("../secret.md", "../../secret.md", "/etc/passwd", "reports/../../../secret.md"):
            assert client.get(f"/api/archive/{bad}/sections").status_code == 404, bad
            assert client.get(f"/api/archive/{bad}/report.md").status_code == 404, bad

    def test_an_empty_results_directory_lists_nothing(self, tmp_path):
        client = TestClient(create_app(RunManager(), results_dir=tmp_path / "missing"))

        assert client.get("/api/archive").json()["reports"] == []


@pytest.mark.unit
def test_the_archive_does_not_sit_under_the_sticky_form_panel():
    """The archive is long-form reading, and the form panel beside it is sticky
    and taller than a laptop viewport, so it stays pinned while the page scrolls.

    A panel spanning the form's column would scroll underneath that pinned,
    opaque panel, which hid the first words of every line — reported as the
    report text being cut off on the left. The archive must keep to the reading
    column the run panel uses, and only drop out of the grid when the layout
    collapses to a single column.
    """
    css = (Path(__file__).parent.parent / "webapp" / "static" / "styles.css").read_text(encoding="utf-8")

    assert ".form-panel { position: sticky;" in css
    assert ".archive-panel { grid-column: 2; }" in css
    assert ".archive-panel { grid-column: 1 / -1" not in css


@pytest.mark.unit
class TestArchiveDelete:
    def test_deleting_needs_an_explicit_confirmation(self, tmp_path):
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-04")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        assert client.delete("/api/archive/reports/AAPL_1").status_code == 400
        assert client.delete("/api/archive/reports/AAPL_1", params={"confirm": "false"}).status_code == 400
        # Refused, not carried out silently: the report is still there.
        assert (tmp_path / "reports" / "AAPL_1" / "complete_report.md").is_file()
        assert [e["id"] for e in client.get("/api/archive").json()["reports"]] == ["reports/AAPL_1"]

    def test_deleting_a_finished_report_removes_its_folder_only(self, tmp_path):
        directory = _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-04")
        sibling = _write_finished_report(tmp_path, "AAPL_2", "AAPL", "2026-11-05")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        response = client.delete("/api/archive/reports/AAPL_1", params={"confirm": "true"})

        assert response.status_code == 200
        assert not directory.exists()
        assert sibling.exists(), "another report under the same ticker must survive"
        assert [e["id"] for e in client.get("/api/archive").json()["reports"]] == ["reports/AAPL_2"]

    def test_deleting_a_run_folder_keeps_the_run_log_and_other_dates(self, tmp_path):
        _write_run_folder(tmp_path, "BTC-USD", "2026-11-04")
        log = tmp_path / "BTC-USD" / "2026-11-04" / "message_tool.log"
        log.write_text("tool log", encoding="utf-8")
        other = _write_run_folder(tmp_path, "BTC-USD", "2026-11-05")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        response = client.delete("/api/archive/BTC-USD/2026-11-04", params={"confirm": "true"})

        assert response.status_code == 200
        assert not (tmp_path / "BTC-USD" / "2026-11-04" / "reports").exists()
        assert log.is_file(), "the run's message log is not the report and must not be deleted"
        assert other.exists(), "the ticker's other analysis dates must survive"

    def test_deleting_the_last_report_prunes_an_emptied_ticker_folder(self, tmp_path):
        _write_finished_report(tmp_path, "ENI.MI_1", "ENI.MI", "2026-11-04")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        client.delete("/api/archive/reports/ENI.MI_1", params={"confirm": "true"})

        assert not (tmp_path / "reports").exists() or not any((tmp_path / "reports").iterdir())

    def test_nothing_outside_the_results_directory_can_be_deleted(self, tmp_path):
        root = tmp_path / "results"
        _write_finished_report(root, "AAPL_1", "AAPL", "2026-11-04")
        secret = tmp_path / "secret.txt"
        secret.write_text("private", encoding="utf-8")
        client = TestClient(create_app(RunManager(), results_dir=root))

        for bad in ("../secret.txt", "../../secret.txt", "/etc/passwd",
                    "reports/../../../secret.txt", "reports", "AAPL"):
            assert client.delete(f"/api/archive/{bad}", params={"confirm": "true"}).status_code == 404, bad

        assert secret.is_file(), "a file outside the results directory must never be deleted"
        assert (root / "reports" / "AAPL_1").exists()

    def test_a_deleted_report_is_gone_from_the_list_and_the_disk(self, tmp_path):
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-04")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        assert client.get("/api/archive/reports/AAPL_1/sections").status_code == 200

        client.delete("/api/archive/reports/AAPL_1", params={"confirm": "true"})

        assert client.get("/api/archive").json()["reports"] == []
        assert client.get("/api/archive/reports/AAPL_1/sections").status_code == 404
        assert client.get("/api/archive/reports/AAPL_1/report.md").status_code == 404

    def test_deleting_an_unknown_report_is_404(self, tmp_path):
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        assert client.delete("/api/archive/reports/NOPE_1", params={"confirm": "true"}).status_code == 404


# ----------------------------------------------------------------- backtest --


class _FakeBacktestGraph:
    """A graph whose propagate records the cell and whose settle settles nothing."""

    last_instance: _FakeBacktestGraph | None = None

    def __init__(self, selected_analysts, config=None):
        self.selected_analysts = list(selected_analysts)
        self.config = config
        self.memory_log = TradingMemoryLog(config)
        self.propagated: list[tuple[str, str]] = []
        _FakeBacktestGraph.last_instance = self

    def propagate(self, ticker, date, asset_type="stock", portfolio=None):
        self.propagated.append((ticker, date))

    def settle_pending(self, ticker):
        from tradingagents.memory.settlement import Settlement

        return Settlement()


@pytest.mark.unit
class TestBacktestApi:
    def test_a_sweep_runs_its_grid_and_reports_the_summary(self, monkeypatch, tmp_path):
        import tradingagents.backtest as backtest_module
        import webapp.backtest_service as backtest_service

        monkeypatch.setattr(backtest_module, "TradingAgentsGraph", _FakeBacktestGraph)
        monkeypatch.setattr(backtest_service, "summarize",
                            lambda result: _SummaryStub())
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        response = client.post("/api/backtests", json={
            "tickers": ["NVDA"], "start_date": "2026-09-01", "end_date": "2026-09-08",
            "every_n_days": 7,
        })
        assert response.status_code == 202
        sweep = response.json()
        assert sweep["cells_total"] == 2

        deadline = time.time() + 5
        while sweep["status"] == "running" and time.time() < deadline:
            time.sleep(0.02)
            sweep = client.get(f"/api/backtests/{sweep['id']}").json()
        assert sweep["status"] == "completed", sweep["error"]
        assert sweep["cells_run"] == 2
        assert sweep["summary"]["resolved"] == 1
        graph = _FakeBacktestGraph.last_instance
        assert graph.propagated == [("NVDA", "2026-09-01"), ("NVDA", "2026-09-08")]
        # The sweep's own log sits under the results directory's backtest folder.
        assert sweep["log_path"] and "/backtest/" in sweep["log_path"]
        assert sweep["log_path"].endswith("trading_memory.md")

    def test_a_second_sweep_while_one_runs_is_refused(self, monkeypatch, tmp_path):
        import tradingagents.backtest as backtest_module

        gate = threading.Event()

        class GatedGraph(_FakeBacktestGraph):
            def propagate(self, ticker, date, asset_type="stock", portfolio=None):
                gate.wait(timeout=5)

        monkeypatch.setattr(backtest_module, "TradingAgentsGraph", GatedGraph)
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        first = client.post("/api/backtests", json={
            "tickers": ["NVDA"], "start_date": "2026-09-01", "end_date": "2026-09-01",
        })
        assert first.status_code == 202
        second = client.post("/api/backtests", json={
            "tickers": ["AAPL"], "start_date": "2026-09-01", "end_date": "2026-09-01",
        })
        assert second.status_code == 422
        assert "already running" in second.json()["detail"]
        gate.set()

    def test_a_bad_grid_is_422_with_the_reason(self, tmp_path):
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        response = client.post("/api/backtests", json={
            "tickers": ["NVDA"], "start_date": "2026-09-08", "end_date": "2026-09-01",
        })
        assert response.status_code == 422
        assert "before" in response.json()["detail"]

        empty = client.post("/api/backtests", json={
            "tickers": [], "start_date": "2026-09-01", "end_date": "2026-09-01",
        })
        assert empty.status_code == 422

    def test_an_unknown_sweep_is_404(self, tmp_path):
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        assert client.get("/api/backtests/nope").status_code == 404
        assert client.post("/api/backtests/nope/cancel").status_code == 404

    def test_cancelling_a_finished_sweep_is_refused(self, monkeypatch, tmp_path):
        import tradingagents.backtest as backtest_module

        monkeypatch.setattr(backtest_module, "TradingAgentsGraph", _FakeBacktestGraph)
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        sweep = client.post("/api/backtests", json={
            "tickers": ["NVDA"], "start_date": "2026-09-01", "end_date": "2026-09-01",
        }).json()
        deadline = time.time() + 5
        while sweep["status"] == "running" and time.time() < deadline:
            time.sleep(0.02)
            sweep = client.get(f"/api/backtests/{sweep['id']}").json()
        assert client.post(f"/api/backtests/{sweep['id']}/cancel").status_code == 409


class _SummaryStub:
    """What summarize returns, shaped like BacktestSummary's fields."""

    resolved = 1
    pending = 1
    unscored = 0
    holding = "5 trading days"

    by_rating = {"Buy": type("S", (), {"count": 1, "hit_rate": 1.0, "mean_alpha": 0.02})()}


# ------------------------------------------------------------ decision log --


@pytest.mark.unit
class TestMemoryApi:
    def test_the_log_lists_its_entries_with_their_outcomes(self, monkeypatch, tmp_path):
        from webapp import memory_view

        log_path = tmp_path / "memory.md"
        log = TradingMemoryLog({"memory_log_path": str(log_path)})
        log.store_decision("NVDA", "2026-09-01", "- **Rating**: Buy\n\nAdd on weakness.", rating="Buy")
        log.update_with_outcome("NVDA", "2026-09-01", 0.03, 0.01, 5, "The call worked.", "2026-09-08")

        monkeypatch.setattr(memory_view, "_log", lambda: log)
        monkeypatch.setattr(memory_view, "log_path", lambda: str(log_path))
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        data = client.get("/api/memory").json()
        assert data["path"] == str(log_path)
        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert entry["ticker"] == "NVDA"
        assert entry["rating"] == "Buy"
        assert entry["pending"] is False
        assert entry["alpha"] == "+1.0%"
        assert "Add on weakness" in entry["decision"]
        assert "worked" in entry["reflection"]

    def test_an_empty_log_lists_nothing(self, tmp_path):
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        data = client.get("/api/memory").json()
        assert data["entries"] == []

    def test_settlement_runs_off_the_request_and_reports_its_result(self, monkeypatch, tmp_path):
        from webapp import memory_view

        log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
        monkeypatch.setattr(memory_view, "_log", lambda: log)

        class _Result:
            settled = [("NVDA", "2026-09-01")]
            failed = [("AAPL", "prices unavailable")]

        monkeypatch.setattr(memory_view, "settle_all_pending", lambda *a, **k: _Result())
        monkeypatch.setattr(memory_view, "create_tier_client",
                            lambda *a, **k: type("C", (), {"get_llm": lambda self: "llm"})())
        monkeypatch.setattr(memory_view, "Reflector", lambda *a: None)

        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        assert client.post("/api/memory/settle").status_code == 202
        deadline = time.time() + 5
        status = {}
        while time.time() < deadline:
            status = client.get("/api/memory/settle/status").json()
            if status["status"] != "running":
                break
            time.sleep(0.02)
        assert status["status"] == "completed"
        assert status["settled"] == [{"ticker": "NVDA", "date": "2026-09-01"}]
        assert status["failed"] == [{"ticker": "AAPL", "reason": "prices unavailable"}]

    def test_a_second_settlement_while_one_runs_is_refused(self, monkeypatch, tmp_path):
        from webapp import memory_view

        gate = threading.Event()

        def slow_settle(*args, **kwargs):
            gate.wait(timeout=5)
            class _Result:
                settled = []
                failed = []
            return _Result()

        log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")})
        monkeypatch.setattr(memory_view, "_log", lambda: log)
        monkeypatch.setattr(memory_view, "settle_all_pending", slow_settle)
        monkeypatch.setattr(memory_view, "create_tier_client",
                            lambda *a, **k: type("C", (), {"get_llm": lambda self: "llm"})())
        monkeypatch.setattr(memory_view, "Reflector", lambda *a: None)

        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        assert client.post("/api/memory/settle").status_code == 202
        assert client.post("/api/memory/settle").status_code == 409
        gate.set()


# ------------------------------------------------------------------- chart --


@pytest.mark.unit
class TestChartApi:
    def test_closes_come_back_as_dates_and_prices(self, monkeypatch, tmp_path):
        import pandas as pd

        from webapp import chart as chart_module

        closes = pd.Series(
            [100.0, 101.0, 102.0, 103.0],
            index=pd.DatetimeIndex(["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]),
        )
        monkeypatch.setattr(chart_module, "get_closes", lambda *a, **k: closes)
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        data = client.get("/api/chart/NVDA", params={"date": "2026-08-06"}).json()
        assert data["ticker"] == "NVDA"
        assert [c["date"] for c in data["closes"]] == ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
        assert data["closes"][-1]["close"] == 103.0

    def test_a_historical_date_never_sees_later_bars(self, monkeypatch, tmp_path):
        import pandas as pd

        from webapp import chart as chart_module

        closes = pd.Series(
            [100.0, 101.0, 102.0],
            index=pd.DatetimeIndex(["2026-08-03", "2026-08-04", "2026-08-05"]),
        )
        monkeypatch.setattr(chart_module, "get_closes", lambda *a, **k: closes)
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        data = client.get("/api/chart/NVDA", params={"date": "2026-08-04"}).json()
        assert all(c["date"] <= "2026-08-04" for c in data["closes"])

    def test_no_prices_is_an_empty_chart_not_an_error(self, monkeypatch, tmp_path):
        import pandas as pd

        from webapp import chart as chart_module

        monkeypatch.setattr(chart_module, "get_closes", lambda *a, **k: pd.Series(dtype=float))
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        data = client.get("/api/chart/NVDA", params={"date": "2026-08-04"}).json()
        assert data["closes"] == []


# ----------------------------------------------------------------- compare --


@pytest.mark.unit
class TestCompare:
    def test_two_reports_are_paired_by_agent(self, tmp_path):
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-01")
        _write_finished_report(tmp_path, "AAPL_2", "AAPL", "2026-11-03")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        data = client.get("/api/archive/compare",
                          params={"left": "reports/AAPL_1", "right": "reports/AAPL_2"}).json()
        titles = [s["title"] for s in data["sections"]]
        assert "Market Analyst" in titles
        market = next(s for s in data["sections"] if s["title"] == "Market Analyst")
        assert "Uptrend intact." in market["left_html"]
        assert "Uptrend intact." in market["right_html"]

    def test_a_section_one_report_lacks_is_shown_as_missing(self, tmp_path):
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-01")
        # The second report has no sections at all: an empty tree still lists.
        directory = tmp_path / "reports" / "AAPL_2"
        directory.mkdir(parents=True)
        (directory / "complete_report.md").write_text(
            "# Trading Analysis Report: AAPL\n\n- Analysis date: 2026-11-03\n", encoding="utf-8")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        data = client.get("/api/archive/compare",
                          params={"left": "reports/AAPL_1", "right": "reports/AAPL_2"}).json()
        market = next(s for s in data["sections"] if s["title"] == "Market Analyst")
        assert market["left_html"]
        assert market["right_html"] is None

    def test_an_unknown_report_is_404(self, tmp_path):
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-01")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        response = client.get("/api/archive/compare",
                              params={"left": "reports/AAPL_1", "right": "reports/NOPE"})
        assert response.status_code == 404


# ------------------------------------------------------------------- rerun --


@pytest.mark.unit
class TestRerun:
    def test_the_header_records_what_the_form_needs(self, tmp_path):
        directory = _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-01", "Buy")
        (directory / "complete_report.md").write_text(
            "# Trading Analysis Report: AAPL\n\n"
            "- Analysis date: 2026-11-01\n"
            "- Rating: Buy\n"
            "- Generated: 2026-11-01 12:00:00\n"
            "- TradingAgents 0.7.1: openai, deep gpt-6-sol, quick gpt-6-luna\n"
            "- Analysts: market, sentiment, news; research debate rounds 3, risk debate rounds 3\n\n"
            "## I. Analyst Team Reports\n\n### Market Analyst\nA strong quarter.\n",
            encoding="utf-8")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))

        settings = client.get("/api/archive/reports/AAPL_1/rerun").json()
        assert settings["ticker"] == "AAPL"
        assert settings["analysis_date"] == "2026-11-01"
        assert settings["analysts"] == ["market", "social", "news"]
        assert settings["research_depth"] == 3
        assert settings["quick_think_llm"] == "gpt-6-luna"
        assert settings["deep_think_llm"] == "gpt-6-sol"

    def test_a_report_without_settings_still_names_ticker_and_date(self, tmp_path):
        _write_finished_report(tmp_path, "AAPL_1", "AAPL", "2026-11-01")
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        settings = client.get("/api/archive/reports/AAPL_1/rerun").json()
        assert settings["ticker"] == "AAPL"
        assert settings["analysis_date"] == "2026-11-01"
        assert settings["analysts"] == []

    def test_an_unknown_report_is_404(self, tmp_path):
        client = TestClient(create_app(RunManager(), results_dir=tmp_path))
        assert client.get("/api/archive/reports/NOPE/rerun").status_code == 404
