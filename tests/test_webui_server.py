"""The browser UI's HTTP server, driven over real HTTP with a fake graph and no LLM."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest
from langchain_core.messages import AIMessage

from cli import main as cli_main
from cli.webui import server
from cli.webui.jobs import JobRegistry
from tradingagents.graph import trading_graph

pytestmark = pytest.mark.unit

DECISION = "**Rating**: Overweight\n\nAdd on weakness."
JUDGMENTS = {
    "window": ["2026-08-25", "2026-09-01"], "band": "Mildly Bullish", "score": 6.5,
    "confidence": "low", "kept": 1, "total": 2, "dropped": {"injection": 1},
    "sources": {"news": {"stance": 0.3, "kept": 1}}, "spread": 0.0, "unavailable": [],
    "items": [],
}
CHUNKS = [
    {"messages": [AIMessage(content="Reading the tape", id="m1")], "trade_date": "2026-09-01",
     "market_report": "## Trend\nUp."},
    {"messages": [], "sentiment_report": "**Overall: Mildly Bullish**",
     "sentiment_judgments": JUDGMENTS},
    {"messages": [], "risk_debate_state": {"judge_decision": DECISION}},
    {"messages": [], "final_trade_decision": DECISION},
]


class FakeGraph:
    def __init__(self, analysts, config, debug, callbacks):
        self.config = config
        self.graph = self
        self.propagator = self

    def create_run_state(self, *a):
        return {}

    def get_graph_args(self, callbacks):
        return {}

    def begin_checkpoint(self, *a):
        return None

    def checkpoint_input(self, state):
        return state

    def stream(self, state, **args):
        yield from CHUNKS

    def record_decision(self, ticker, date, state):
        from tradingagents.agents.utils.memory import TradingMemoryLog

        TradingMemoryLog(self.config).store_decision(ticker, date, state["final_trade_decision"])

    def clear_checkpoint_on_success(self, *a):
        pass

    def end_checkpoint(self):
        pass

    def process_signal(self, text):
        return "Overweight"


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(trading_graph, "TradingAgentsGraph", FakeGraph)
    # Other tests reload default_config, so the server and cli.main may hold different dicts.
    for config in {id(c): c for c in (server.DEFAULT_CONFIG, cli_main.DEFAULT_CONFIG)}.values():
        monkeypatch.setitem(config, "results_dir", str(tmp_path / "results"))
        monkeypatch.setitem(config, "memory_log_path", str(tmp_path / "memory" / "log.md"))
    monkeypatch.setattr(server, "load_last_run", lambda: {})
    monkeypatch.setattr(server, "save_last_run", lambda selections: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    httpd = server.make_server("127.0.0.1", 0, JobRegistry())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def call(base, path, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers={
        "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            raw = res.read()
            kind = res.headers.get("Content-Type", "")
            return res.status, json.loads(raw) if kind.startswith("application/json") else raw
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


SETTINGS = {"provider": "openai", "quick": "gpt-5.4-mini", "deep": "gpt-5.5",
            "depth": "Shallow", "language": "English", "checkpoint": False}


def _wait_done(base, job_id):
    for _ in range(100):
        status, detail = call(base, f"/api/analyses/{job_id}")
        assert status == 200
        if detail["status"] not in ("pending", "running"):
            return detail
        time.sleep(0.05)
    raise AssertionError("the run did not finish")


def test_pages_and_static_files_are_served(base):
    for path in ("/", "/analyze", "/reports", "/backtest", "/sentiment", "/static/app.js"):
        status, body = call(base, path)
        assert status == 200, path
        assert body
    assert call(base, "/static/../server.py")[0] == 404
    assert call(base, "/static/%2e%2e/server.py")[0] == 404


def test_options_offer_providers_models_and_key_status(base):
    status, options = call(base, "/api/options")
    assert status == 200
    openai = next(p for p in options["providers"] if p["key"] == "openai")
    assert openai["apiKey"] == {"env": "OPENAI_API_KEY", "set": True, "note": ""}
    assert openai["models"]["quick"] and openai["effort"]["label"] == "Reasoning effort"
    assert any(p["key"] == "qwen-cn" and p["china"] for p in options["providers"])
    assert options["defaults"]["analysts"] == ["market", "social", "news", "fundamentals"]


def test_an_analysis_runs_to_a_saved_report_with_its_judgments(base):
    status, started = call(base, "/api/analyses", {
        "ticker": "nvda", "date": "2026-09-01", "analysts": ["market", "social"],
        "settings": SETTINGS})
    assert status == 201, started
    detail = _wait_done(base, started["id"])
    assert detail["status"] == "done", detail["error"]
    assert (detail["ticker"], detail["rating"]) == ("NVDA", "Overweight")
    assert detail["judgments"] == JUDGMENTS
    assert [t for t, agents in detail["teams"]][0] == "Analyst Team"
    assert any(r["kind"] == "Agent" for r in detail["activity"])

    status, markdown = call(base, f"/api/analyses/{started['id']}/report.md")
    assert status == 200 and b"Analysis date: 2026-09-01" in markdown

    status, reports = call(base, "/api/reports")
    [report] = reports
    assert (report["ticker"], report["date"], report["rating"]) == ("NVDA", "2026-09-01", "Overweight")
    assert report["hasJudgments"]
    status, full = call(base, "/api/report?id=" + report["id"])
    assert full["sections"][-1]["title"] == "V. Portfolio Manager Decision"
    assert call(base, "/api/report/judgments?id=" + report["id"]) == (200, JUDGMENTS)

    status, log = call(base, "/api/decisions")
    assert [(r["ticker"], r["rating"], r["status"]) for r in log] == [("NVDA", "Overweight", "pending")]


def test_a_missing_api_key_is_refused_before_a_run_starts(base, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    status, body = call(base, "/api/analyses", {
        "ticker": "NVDA", "date": "2026-09-01", "analysts": ["market"], "settings": SETTINGS})
    assert status == 400 and "OPENAI_API_KEY" in body["error"]
    assert call(base, "/api/analyses") == (200, [])

    assert call(base, "/api/key", {"env": "PATH", "value": "x"})[0] == 400
    assert call(base, "/api/key", {"env": "OPENAI_API_KEY", "value": "k"}) == (200, {"ok": True})


@pytest.mark.parametrize("body, message", [
    ({"ticker": "NV/DA", "date": "2026-09-01", "analysts": ["market"]}, "Tickers"),
    ({"ticker": "NVDA", "date": "2999-01-01", "analysts": ["market"]}, "future"),
    ({"ticker": "NVDA", "date": "2026-09-01", "analysts": []}, "analyst"),
    ({"ticker": "BTC-USD", "date": "2026-09-01", "analysts": ["fundamentals"]}, "analyst"),
    ({"ticker": "NVDA", "date": "2026-09-01", "analysts": ["market"], "portfolio": {"cash": "lots"}},
     "portfolio"),
])
def test_bad_analysis_requests_say_what_is_wrong(base, body, message):
    status, reply = call(base, "/api/analyses", {**body, "settings": SETTINGS})
    assert status == 400
    assert message in reply["error"]


def test_cross_origin_posts_are_refused(base):
    status, body = call(base, "/api/analyses", {"ticker": "NVDA"},
                        headers={"Origin": "https://evil.example"})
    assert status == 403


def test_only_listed_reports_can_be_opened(base):
    assert call(base, "/api/report?id=../../etc/passwd")[0] == 404
    assert call(base, "/api/decisions?run=nope")[0] == 404


def test_backtest_requests_validate_the_grid(base):
    status, body = call(base, "/api/backtests", {
        "tickers": "NVDA", "from": "2026-09-10", "to": "2026-09-01", "every": 7,
        "analysts": ["market"], "settings": SETTINGS})
    assert status == 400 and "before it starts" in body["error"]
    assert call(base, "/api/backtests") == (200, {"runs": [], "jobs": []})
