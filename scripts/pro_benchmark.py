"""Performance benchmarks for the Pro stack (fake LLM = orchestration cost).

    ~/.venvs/tradingagents-pro/bin/python scripts/pro_benchmark.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.pro_fakes import make_bars  # noqa: E402
from tests.test_pro_memory_facade import make_recommendation  # noqa: E402
from tests.test_pro_pipeline_graph import (  # noqa: E402
    CONFIG,
    FakePipelineLLM,
    pipeline_snapshot,
)
from tradingagents.contracts import AssetClass, ProConfig, TradingMode
from tradingagents.pro.backtest import BacktestEngine, BarReplay, SimBroker
from tradingagents.pro.memory import ProMemory
from tradingagents.pro.pipeline import run_pipeline


def timeit(label: str, fn, repeat: int = 3) -> None:
    timings = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        timings.append(time.perf_counter() - start)
    print(f"{label:<48} best {min(timings) * 1000:8.1f} ms  "
          f"mean {sum(timings) / len(timings) * 1000:8.1f} ms")


def main() -> None:
    snapshot = pipeline_snapshot()
    timeit("pipeline run (59 agents, sequential fakes)",
           lambda: run_pipeline(FakePipelineLLM(), CONFIG, snapshot))
    timeit("pipeline run (agent_workers=8)",
           lambda: run_pipeline(FakePipelineLLM(), CONFIG, snapshot, agent_workers=8))

    bt_config = ProConfig(asset=AssetClass.GOLD, mode=TradingMode.BACKTEST)
    replay = BarReplay("XAUUSD", AssetClass.GOLD, make_bars(n=200), window=60)
    timeit("backtest (200 bars, decide_every=10)", lambda: BacktestEngine(
        FakePipelineLLM(), bt_config, replay,
        broker=SimBroker(initial_equity=100_000.0),
        min_history=60, decide_every=10,
    ).run(), repeat=1)

    memory = ProMemory()
    for _ in range(1000):
        trade = memory.record_trade(make_recommendation())
        memory.close_trade(trade.id, pnl=1.0)
    timeit("memory analog retrieval @ 2000 records",
           lambda: memory.historical_analogs("XAUUSD trending_up BUY", k=3))


if __name__ == "__main__":
    main()
