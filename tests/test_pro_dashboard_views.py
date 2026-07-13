"""Dashboard view models over a real recorded pipeline run (no FastAPI)."""

import pytest

from tests.test_pro_memory_facade import make_recommendation
from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM, pipeline_snapshot
from tradingagents.contracts import RiskLimits
from tradingagents.pro.backtest import BacktestEngine, BarReplay, SimBroker
from tradingagents.pro.dashboard import PipelineRecorder
from tradingagents.pro.dashboard.service import (
    agent_performance,
    alert_feed,
    backtest_view,
    debate_timeline,
    evidence_panels,
    market_overview,
    memory_insights,
    recommendation_view,
    system_status,
    trade_journal,
)
from tradingagents.pro.execution import (
    VENUES,
    AuditLog,
    CircuitBreaker,
    ExecutionRouter,
    KillSwitch,
    PaperVenueAdapter,
)
from tradingagents.pro.memory import ProMemory


@pytest.fixture()
def recorded():
    memory = ProMemory()
    recorder = PipelineRecorder()
    run = recorder.record_run(
        FakePipelineLLM(), CONFIG, pipeline_snapshot(), memory=memory
    )
    return recorder, run, memory


class TestRunViews:
    def test_market_overview(self, recorded):
        _, run, _ = recorded
        view = market_overview(run)
        assert view["symbol"] == "XAUUSD"
        assert view["execution_status"] == "accepted:paper"
        assert view["regime"] is not None
        assert view["rejected_at"] is None
        assert market_overview(None) == {"status": "no runs yet"}

    def test_recommendation_view_renders_full_schema(self, recorded):
        _, run, _ = recorded
        view = recommendation_view(run.recommendation)
        # every field of the Phase 0 contract is present
        for field in (
            "action", "confidence", "entry_price", "stop_loss", "take_profits",
            "position_size", "market_regime", "evidence", "counterarguments",
            "vote_breakdown", "historical_analogs", "risk_reward",
        ):
            assert field in view, field
        assert view["action"] == "BUY"
        assert view["vote_tally"]["BUY"] >= 1
        assert view["n_evidence"] == len(view["evidence"])
        assert view["invalidation"] is None  # not supplied

    def test_recommendation_view_carries_invalidation(self, recorded):
        _, run, _ = recorded
        view = recommendation_view(
            run.recommendation, invalidation="close below 2300 invalidates"
        )
        assert view["invalidation"] == "close below 2300 invalidates"

    def test_recommendation_view_explains_rejection(self):
        view = recommendation_view(
            None, rejection={"stage": "risk_gate", "reasons": ["stop too wide"]}
        )
        assert view["status"] == "rejected"
        assert view["rejection"]["stage"] == "risk_gate"


def make_router() -> ExecutionRouter:
    limits = RiskLimits()
    return ExecutionRouter(
        adapter=PaperVenueAdapter(VENUES["mt5"]),
        limits=limits,
        kill_switch=KillSwitch(),
        breaker=CircuitBreaker(limits, equity_base=100_000.0),
        audit=AuditLog(),
    )


class TestSystemStatus:
    def test_unattached(self):
        view = system_status(None)
        assert view["attached"] is False
        assert view["trading_halted"] is None
        assert view["live_armed"] is False  # arming absent = all paper

    def test_healthy_router(self):
        router = make_router()
        router.local_book["XAUUSD"] = 5.0
        view = system_status(router, equity=100_000.0)
        assert view["trading_halted"] is False
        assert view["kill_switch"]["engaged"] is False
        assert view["circuit_breaker"]["tripped"] is False
        assert view["open_positions"] == [{"symbol": "XAUUSD", "quantity": 5.0}]
        assert view["equity"] == 100_000.0

    def test_kill_switch_halts(self):
        router = make_router()
        router.kill_switch.engage("operator halt")
        view = system_status(router)
        assert view["trading_halted"] is True
        assert view["kill_switch"]["reason"] == "operator halt"

    def test_tripped_breaker_halts(self):
        router = make_router()
        for _ in range(3):  # default consecutive-loss limit
            router.breaker.record_trade_result(-10.0)
        view = system_status(router)
        assert view["trading_halted"] is True
        assert "consecutive losses" in view["circuit_breaker"]["reason"]


class TestAlertFeed:
    def test_accepted_clean_run_raises_no_alerts(self, recorded):
        recorder, _, _ = recorded
        assert alert_feed(recorder.runs) == {"alerts": []}

    def test_alerts_from_degraded_and_rejected_runs(self, recorded):
        recorder, run, _ = recorded
        run.state["snapshot"] = run.state["snapshot"].model_copy(
            update={"missing_feeds": ["news:quarantined:0", "macro:fred"]}
        )
        run.state["rejection"] = {"stage": "risk_gate", "reasons": ["stop too wide"]}
        run.state["execution_status"] = "blocked:reconciliation"
        feed = alert_feed(recorder.runs)["alerts"]
        severities = {a["severity"] for a in feed}
        assert severities == {"critical", "warning", "info"}
        quarantine = next(a for a in feed if a["severity"] == "critical")
        assert "prompt injection" in quarantine["text"]
        assert all(a["run_id"] == run.run_id for a in feed)

    def test_debate_timeline_orders_speakers(self, recorded):
        _, run, _ = recorded
        view = debate_timeline(run)
        speakers = [e["speaker"] for e in view["entries"]]
        assert "technical_bull" in speakers and "judge" in speakers
        assert speakers.index("technical_bull") < speakers.index("judge")
        assert view["node_sequence"][0] == "prepare"
        assert view["rejection"] is None

    def test_evidence_panels_grouped_by_team(self, recorded):
        _, run, _ = recorded
        panels = evidence_panels(run)
        assert "technical" in panels and panels["technical"]
        entry = panels["technical"][0]
        assert {"agent_id", "direction", "confidence", "claim",
                "data_refs", "sources"} <= set(entry)


class TestPortfolioViews:
    def test_trade_journal_totals(self):
        memory = ProMemory()
        for pnl in (120.0, -60.0):
            trade = memory.record_trade(make_recommendation())
            memory.close_trade(trade.id, pnl=pnl)
        journal = trade_journal(memory)
        assert journal["n_trades"] == 2
        assert journal["total_pnl"] == pytest.approx(60.0)
        assert journal["win_rate"] == pytest.approx(0.5)
        assert journal["entries"][0]["action"] == "BUY"

    def test_backtest_view_with_monte_carlo(self):
        from tests.pro_fakes import make_bars
        from tradingagents.contracts import AssetClass, ProConfig, TradingMode
        from tradingagents.pro.backtest import monte_carlo_summary

        config = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST)
        replay = BarReplay("XAUUSD", AssetClass.GOLD, make_bars(n=140), window=60)
        result = BacktestEngine(
            FakePipelineLLM(), config, replay,
            broker=SimBroker(initial_equity=100_000.0),
            min_history=60, decide_every=10,
        ).run()
        mc = monte_carlo_summary([t.pnl for t in result.trades] * 3, 100_000.0,
                                 n_paths=50) if len(result.trades) >= 1 else None
        view = backtest_view(result, mc)
        assert view["report"]["n_trades"] == len(result.trades)
        assert len(view["equity_curve"]) == len(result.equity_curve)
        if mc:
            assert "monte_carlo" in view
        assert backtest_view(None) == {"status": "no backtest yet"}

    def test_memory_insights_counts_and_lessons(self):
        memory = ProMemory()
        trade = memory.record_trade(make_recommendation())
        memory.close_trade(trade.id, pnl=-10.0, lesson="sized too large for regime")
        insights = memory_insights(memory)
        assert insights["counts"]["trade"] == 1
        assert insights["counts"]["mistake"] == 1
        assert any("sized too large" in item["text"]
                   for item in insights["recent_lessons"])


class TestAgentPerformance:
    def test_hit_rates_scored_against_outcomes(self, recorded):
        recorder, run, memory = recorded
        rec = run.recommendation
        trade = memory.find_trade_by_recommendation(rec.id)
        assert trade is not None  # pipeline recorded it at execution
        memory.close_trade(trade.id, pnl=500.0)  # the BUY won

        perf = agent_performance(recorder.runs, memory)
        assert "judge" in perf
        judge = perf["judge"]
        assert judge["votes"] == 1
        assert judge["scored"] == 1
        assert judge["hit_rate"] == 1.0  # judge voted BUY, trade won
        # every evidence agent voted BUY (fake llm) -> all correct
        assert all(row["hit_rate"] in (None, 1.0) for row in perf.values())

    def test_unscored_agents_have_null_hit_rate(self, recorded):
        recorder, run, memory = recorded  # trade never closed
        perf = agent_performance(recorder.runs, memory)
        assert all(row["hit_rate"] is None for row in perf.values())
        assert all(row["votes"] >= 1 for row in perf.values())
