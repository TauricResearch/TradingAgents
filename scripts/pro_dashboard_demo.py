"""Run the Pro dashboard with seeded demo state (fake LLM, synthetic data).

    python scripts/pro_dashboard_demo.py  [PORT]

Everything shown is produced by the real pipeline/backtest code paths —
only the LLM responses and bars are synthetic.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root: test fakes

from tests.pro_fakes import BASE_TS  # noqa: E402
from tests.test_pro_pipeline_graph import FakePipelineLLM, pipeline_snapshot  # noqa: E402
from tradingagents.contracts import (
    AssetClass,
    OHLCVBar,
    ProConfig,
    RiskLimits,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import (
    BacktestEngine,
    BarReplay,
    SimBroker,
    monte_carlo_summary,
)
from tradingagents.pro.dashboard import marketdata as md, service as dashboard_service
from tradingagents.pro.dashboard.app import DashboardState, create_app
from tradingagents.pro.execution import (
    VENUES,
    AuditLog,
    CircuitBreaker,
    ExecutionRouter,
    KillSwitch,
    PaperVenueAdapter,
)
from tradingagents.pro.memory import ProMemory


def wavy_bars(n: int = 300) -> list[OHLCVBar]:
    """Rising bars with pullbacks so the demo shows wins AND losses."""
    bars, price = [], 2300.0
    for i in range(n):
        drift = 1.2 if (i // 25) % 3 != 2 else -1.6  # two legs up, one down
        close = price + drift
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=max(price, close) + 4.0, low=min(price, close) - 4.0,
            close=close, volume=5_000.0,
        ))
        price = close
    return bars


class _DemoMarket(md.MarketDataService):
    """Deterministic synthetic bars for ANY (symbol, timeframe), spaced by
    the REQUESTED timeframe and anchored just past the seeded run's as-of —
    so chart windows cover the recorded run (annotations snap onto them)
    and the Backtest page pages arbitrarily deep history, all offline."""

    anchor = BASE_TS + timedelta(days=36)  # recorded run as-of ≈ BASE_TS+35.6d
    history_bars = 200_000  # paging depth: effectively unlimited for the demo

    @staticmethod
    def _price(i: int) -> float:
        # closed-form wavy walk (two 25-bar legs up, one down → +20/75 bars)
        cycles, pos = divmod(i, 75)
        price = 2300.0 + 20.0 * cycles
        up = min(pos, 50)
        price += 1.2 * up - 1.6 * (pos - up)
        return price

    def get_bars(self, symbol, timeframe, limit=md.DEFAULT_LIMIT, end=None):
        step = md.TIMEFRAME_SECONDS[timeframe]
        # bar i starts at anchor - (history_bars - i)*step; the last bar
        # strictly before ``end`` excludes floor((anchor-end)/step) newest
        excluded = 0
        if end is not None and end < self.anchor:
            excluded = int((self.anchor - end).total_seconds() // step)
        last = self.history_bars - 1 - excluded
        limit = min(limit, md.MAX_LIMIT)
        first = max(0, last - limit + 1)
        bars = []
        for i in range(first, last + 1):
            open_, close = self._price(i), self._price(i + 1)
            bars.append(OHLCVBar(
                timeframe=timeframe,
                start=self.anchor - timedelta(seconds=(self.history_bars - i) * step),
                open=open_, high=max(open_, close) + 4.0,
                low=min(open_, close) - 4.0, close=close, volume=5_000.0,
            ))
        return bars


def build_state() -> DashboardState:
    state = DashboardState(memory=ProMemory())
    state.marketdata = _DemoMarket()
    config = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST)

    replay = BarReplay("XAUUSD", AssetClass.GOLD, wavy_bars(), window=100)
    result = BacktestEngine(
        FakePipelineLLM(), config, replay,
        broker=SimBroker(initial_equity=100_000.0),
        memory=state.memory, min_history=100, decide_every=7,
    ).run()
    state.backtest = result
    if len(result.trades) >= 2:
        state.monte_carlo = monte_carlo_summary(
            [t.pnl for t in result.trades], 100_000.0, n_paths=500
        )

    paper_config = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1)
    run = state.recorder.record_run(
        FakePipelineLLM(), paper_config, pipeline_snapshot(), memory=state.memory
    )
    # demo-only: mark two feeds degraded so the alert stream has content
    run.state["snapshot"] = run.state["snapshot"].model_copy(
        update={"missing_feeds": ["news:quarantined:0", "macro:fred"]}
    )

    # attach an execution router so /api/status shows the real safety rails
    state.router = ExecutionRouter(
        adapter=PaperVenueAdapter(VENUES["mt5"]),
        limits=RiskLimits(),
        kill_switch=KillSwitch(),
        breaker=CircuitBreaker(RiskLimits(), equity_base=100_000.0),
        audit=AuditLog(),
    )
    if run.recommendation is not None:  # mirror the accepted paper fill
        # submit through the router so the paper venue holds the matching
        # position — otherwise reconcile() flags drift on the next run
        state.router.submit_recommendation(run.recommendation, equity=100_000.0)
    state.equity = result.final_equity

    # on-demand trigger backed by the fake LLM so the Run Pipeline dialog
    # is fully exercisable (and e2e-testable) without cost or network
    from tradingagents.pro.main import PipelineTrigger
    from tradingagents.pro.service import PaperTradingService

    service = PaperTradingService(
        FakePipelineLLM(), paper_config, pipeline_snapshot,
        router=state.router, memory=state.memory, dashboard_state=state,
        on_event=state.broadcaster.publish,
    )

    class DemoTrigger(PipelineTrigger):
        def _build_snapshot(self, symbol, asset, tf):  # no vendors in demo
            return pipeline_snapshot()

    state.trigger = DemoTrigger(service)

    # PRO_DEMO_ARM=BTC-USD:canary arms a pair so the live banner +
    # Emergency Flatten control are exercisable in the demo (go-live P4).
    import os

    # seed one auto-archived backtest run so the Saved Runs list + result
    # view render on first load (and the e2e can reload it without a network run)
    from tradingagents.pro.dashboard.backtest_artifacts import RunArtifacts
    from tradingagents.pro.dashboard.backtest_job import (
        closed_trade_view,
        summary_from_view,
    )

    seeded_view = dashboard_service.backtest_view(result, state.monte_carlo)
    equity_rows = [[t.isoformat(), e] for t, e in zip(
        (b.start for b in wavy_bars()[100:]), seeded_view.pop("equity_curve", []),
        strict=False)]
    seeded_view.update({
        "provider": "deterministic", "symbol": "XAUUSD", "timeframe": "1d",
        "duration": "30D", "window": ["2024-01-01", "2024-10-26"],
        "status": "done", "indicator_mode": "windowed",
        "initial_equity": 100_000.0,
    })
    RunArtifacts("demo-seed").write(
        equity=equity_rows,
        trades=[closed_trade_view(t) for t in result.trades],
        decisions=[],
    )
    seed_created = BASE_TS.isoformat()
    state.backtest_runs.save({
        "id": "demo-seed", "created_at": seed_created,
        "params": {"symbol": "XAUUSD", "timeframe": "1d", "duration": "30D"},
        "status": "done",
        "summary": summary_from_view("demo-seed", seed_created, seeded_view),
        "view": seeded_view,
    })

    demo_arm = os.environ.get("PRO_DEMO_ARM")
    if demo_arm:
        import tempfile
        from pathlib import Path

        from tradingagents.pro.arming import ArmingStore

        pair, _, tier = demo_arm.partition(":")
        arming = ArmingStore(Path(tempfile.mkdtemp()) / "arming.json",
                             audit=state.router.audit)
        arming.arm(pair, tier or "canary", operator="demo")
        state.arming = arming
    return state


def main() -> None:
    import uvicorn

    try:  # pick up gitignored keys (OANDA_API_TOKEN etc.) for dev servers
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass

    # PORT env var (dev-tool auto-assigned port) wins over the CLI arg so
    # this can share a machine with other chats' demo servers; CLI arg stays
    # for manual `python scripts/pro_dashboard_demo.py <port>` runs.
    if os.environ.get("PORT"):
        port = int(os.environ["PORT"])
    elif len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = 8600
    uvicorn.run(create_app(build_state()), host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
