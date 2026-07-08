"""Run the Pro dashboard with seeded demo state (fake LLM, synthetic data).

    python scripts/pro_dashboard_demo.py  [PORT]

Everything shown is produced by the real pipeline/backtest code paths —
only the LLM responses and bars are synthetic.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root: test fakes
from tests.pro_fakes import BASE_TS  # noqa: E402
from tests.test_pro_pipeline_graph import FakePipelineLLM, pipeline_snapshot  # noqa: E402
from tradingagents.contracts import AssetClass, OHLCVBar, ProConfig, Timeframe, TradingMode
from tradingagents.pro.backtest import (
    BacktestEngine,
    BarReplay,
    SimBroker,
    monte_carlo_summary,
)
from tradingagents.pro.dashboard.app import DashboardState, create_app
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


def build_state() -> DashboardState:
    state = DashboardState(memory=ProMemory())
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
    state.recorder.record_run(
        FakePipelineLLM(), paper_config, pipeline_snapshot(), memory=state.memory
    )
    return state


def main() -> None:
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8600
    uvicorn.run(create_app(build_state()), host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
