"""FastAPI application for the Pro dashboard.

Requires the ``dashboard`` extra (``pip install "tradingagents[dashboard]"``).
The app is a thin shell: every endpoint delegates to the tested view-model
functions in service.py; the single HTML page renders them with vanilla JS.

Run locally:
    uvicorn --factory tradingagents.pro.dashboard.app:create_default_app
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources

from tradingagents.pro.backtest import BacktestResult
from tradingagents.pro.dashboard import service
from tradingagents.pro.dashboard.recorder import PipelineRecorder, RunRecord
from tradingagents.pro.memory import ProMemory


@dataclass
class DashboardState:
    recorder: PipelineRecorder = field(default_factory=PipelineRecorder)
    memory: ProMemory = field(default_factory=ProMemory)
    backtest: BacktestResult | None = None
    monte_carlo = None

    @property
    def runs(self) -> list[RunRecord]:
        return self.recorder.runs

    def latest_run(self) -> RunRecord | None:
        return self.runs[-1] if self.runs else None


def create_app(state: DashboardState | None = None):
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse

    state = state or DashboardState()
    app = FastAPI(title="TradingAgents Pro Dashboard")
    app.state.dashboard = state

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (
            resources.files("tradingagents.pro.dashboard")
            .joinpath("templates", "dashboard.html")
            .read_text(encoding="utf-8")
        )

    @app.get("/api/overview")
    def overview() -> dict:
        return service.market_overview(state.latest_run())

    @app.get("/api/runs")
    def runs() -> list[dict]:
        return [
            {
                "run_id": run.run_id,
                "started_at": run.started_at.isoformat(),
                "symbol": run.symbol,
                "action": run.recommendation.action.value if run.recommendation else None,
                "rejected_at": run.rejection and run.rejection.get("stage"),
            }
            for run in state.runs
        ]

    def _run_or_404(run_id: str) -> RunRecord:
        for run in state.runs:
            if run.run_id == run_id:
                return run
        raise HTTPException(status_code=404, detail=f"no run {run_id}")

    @app.get("/api/runs/{run_id}/timeline")
    def timeline(run_id: str) -> dict:
        return service.debate_timeline(_run_or_404(run_id))

    @app.get("/api/runs/{run_id}/evidence")
    def evidence(run_id: str) -> dict:
        return service.evidence_panels(_run_or_404(run_id))

    @app.get("/api/recommendation/latest")
    def latest_recommendation() -> dict:
        run = state.latest_run()
        return service.recommendation_view(run.recommendation if run else None)

    @app.get("/api/journal")
    def journal() -> dict:
        return service.trade_journal(state.memory)

    @app.get("/api/backtest")
    def backtest() -> dict:
        return service.backtest_view(state.backtest, state.monte_carlo)

    @app.get("/api/memory")
    def memory_view() -> dict:
        return service.memory_insights(state.memory)

    @app.get("/api/agents")
    def agents() -> dict:
        return service.agent_performance(state.runs, state.memory)

    return app


def create_default_app():
    """uvicorn --factory entry point with empty state."""
    return create_app()
