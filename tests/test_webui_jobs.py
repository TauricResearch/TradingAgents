"""The web UI's background jobs and history readers, without Streamlit or an LLM."""

import threading

import pytest
from langchain_core.messages import AIMessage

from cli.webui import jobs
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.graph import trading_graph

pytestmark = pytest.mark.unit

DECISION = "**Rating**: Buy\n\nAdd on weakness."
CHUNKS = [
    {"messages": [AIMessage(content="Looking at price action", id="m1",
                            tool_calls=[{"name": "get_stock_data", "args": {"symbol": "NVDA"},
                                         "id": "t1"}])]},
    {"messages": [], "market_report": "## Trend\nUptrend intact."},
    {"messages": [], "investment_debate_state": {"bull_history": "Bull case", "bear_history": "",
                                                 "judge_decision": "Go long"}},
    {"messages": [], "trader_investment_plan": "Buy 10 units"},
    {"messages": [], "risk_debate_state": {"aggressive_history": "More", "conservative_history": "",
                                           "neutral_history": "", "judge_decision": DECISION}},
    {"messages": [], "final_trade_decision": DECISION},
]


class FakeGraph:
    """Just the surface AnalysisJob drives; streams CHUNKS, optionally one at a time."""

    gate: threading.Event | None = None

    def __init__(self, analysts, config, debug, callbacks):
        self.config = config
        self.recorded = None
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
        for chunk in CHUNKS:
            if FakeGraph.gate is not None:
                FakeGraph.gate.wait(5)
            yield chunk

    def record_decision(self, ticker, date, state):
        TradingMemoryLog(self.config).store_decision(ticker, date, state["final_trade_decision"])

    def clear_checkpoint_on_success(self, *a):
        pass

    def end_checkpoint(self):
        pass

    def process_signal(self, text):
        return "Buy" if "Buy" in text else "REVIEW"


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setattr(trading_graph, "TradingAgentsGraph", FakeGraph)
    FakeGraph.gate = None
    return {"results_dir": str(tmp_path / "results"),
            "memory_log_path": str(tmp_path / "memory" / "log.md")}


def _finish(job):
    job._thread.join(5)
    assert not job._thread.is_alive()


def test_analysis_job_runs_to_a_saved_report(config):
    job = jobs.AnalysisJob("NVDA", "2026-09-01", "stock", ["market"], config).start()
    _finish(job)

    snap = job.snapshot()
    assert snap["status"] == jobs.DONE, snap["error"]
    assert snap["rating"] == "Buy"
    assert set(snap["agent_status"].values()) == {"completed"}
    assert snap["sections"]["market_report"] == "## Trend\nUptrend intact."
    assert snap["sections"]["final_trade_decision"] == DECISION
    assert any(name == "get_stock_data" for _, name, _ in snap["tool_calls"])
    assert snap["report_path"].exists()

    [saved] = jobs.list_saved_reports(config["results_dir"])
    assert saved.ticker == "NVDA"
    sections = jobs.load_report_sections(saved)
    # An agent's own "## " heading stays inside its section.
    assert [title for title, _ in sections] == [
        "I. Analyst Team Reports", "II. Research Team Decision", "III. Trading Team Plan",
        "IV. Risk Management Team Decision", "V. Portfolio Manager Decision",
    ]
    assert "## Trend" in sections[0][1]

    [row] = jobs.load_decisions(config["memory_log_path"])
    assert (row["ticker"], row["rating"], row["status"]) == ("NVDA", "Buy", "pending")


def test_analysis_job_stops_when_cancelled(config):
    FakeGraph.gate = threading.Event()
    job = jobs.AnalysisJob("NVDA", "2026-09-01", "stock", ["market"], config).start()
    job.cancel()
    FakeGraph.gate.set()
    _finish(job)
    assert job.status == jobs.CANCELLED
    assert jobs.load_decisions(config["memory_log_path"]) == []


def test_analysis_job_reports_a_failure(config, monkeypatch):
    def boom(self, *a):
        raise RuntimeError("vendor down")

    monkeypatch.setattr(FakeGraph, "create_run_state", boom)
    job = jobs.AnalysisJob("NVDA", "2026-09-01", "stock", ["market"], config).start()
    _finish(job)
    assert job.status == jobs.FAILED
    assert "vendor down" in job.error


def test_analysis_job_needs_an_analyst(config):
    with pytest.raises(ValueError):
        jobs.AnalysisJob("NVDA", "2026-09-01", "stock", ["bogus"], config)


def test_state_logs_are_listed_and_readable(tmp_path):
    logs = tmp_path / "AAPL" / "TradingAgentsStrategy_logs"
    logs.mkdir(parents=True)
    (logs / "full_states_log_2026-08-03.json").write_text(
        '{"market_report": "Flat.", "trader_investment_decision": "Hold",'
        ' "investment_debate_state": {}, "risk_debate_state": {"judge_decision": "Hold"}}',
        encoding="utf-8")
    [report] = jobs.list_saved_reports(tmp_path)
    assert (report.ticker, report.trade_date, report.kind) == ("AAPL", "2026-08-03", "state")
    sections = dict(jobs.load_report_sections(report))
    assert "Trader" in sections["III. Trading Team Plan"]
    assert "Hold" in sections["V. Portfolio Manager Decision"]


def test_settled_decisions_read_as_fractions(tmp_path):
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "log.md")})
    log.store_decision("NVDA", "2026-08-03", DECISION)
    log.update_with_outcome("NVDA", "2026-08-03", 0.042, -0.013, 5, "Fine.")
    [row] = jobs.load_decisions(tmp_path / "log.md")
    assert row["status"] == "settled"
    assert row["return"] == pytest.approx(0.042)
    assert row["alpha"] == pytest.approx(-0.013)
