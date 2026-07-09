"""Live-data terminal: one REAL model decision on today's tape, served.

    python scripts/pro_live_terminal.py [port]

- Snapshot: build_gold_pipeline() — live yfinance GC=F daily bars,
  DXY/US10Y/silver cross-asset, FRED macro (if keyed), real session;
  every feed failure lands in missing_feeds, disclosed on the dashboard.
- Decision: one PaperTradingService.run_once() with real models from
  TRADINGAGENTS_* env (default deepseek via repo .env), full safety
  rails (kill switch armed, breaker, hash-chained audit in a temp dir).
- Serving: the dashboard on :8600 with live Delta Exchange charts/ticks
  (BTCUSD perp, XAUTUSD Tether Gold) when reachable.

A rejection is as valid an outcome as a trade — the gates saying no to
today's market is the system working.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradingagents.contracts import AssetClass, ModelRouting, ProConfig, RiskLimits  # noqa: E402


def main() -> None:
    import uvicorn
    from dotenv import load_dotenv

    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(repo_root / ".env")

    from tradingagents.pro.alerting import AlertManager, LogAlertSink
    from tradingagents.pro.dashboard.app import DashboardState, create_app
    from tradingagents.pro.dashboard.events import BroadcastAlertSink
    from tradingagents.pro.execution import (
        VENUES,
        AuditLog,
        CircuitBreaker,
        ExecutionRouter,
        KillSwitch,
        PaperVenueAdapter,
    )
    from tradingagents.pro.ingestion.builder import build_gold_pipeline
    from tradingagents.pro.memory import ProMemory
    from tradingagents.pro.models import bundle_from_config
    from tradingagents.pro.observability import CostTrackingLLM, price_for
    from tradingagents.pro.service import PaperTradingService

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8600

    routing = ModelRouting(
        llm_provider=os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "deepseek"),
        quick_think_llm=os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", "deepseek-chat"),
        deep_think_llm=os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "deepseek-chat"),
    )
    config = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1, models=routing)

    print(f"building real model bundle ({routing.llm_provider})…")
    bundle = bundle_from_config(config, temperature=0.2)
    price = price_for(routing.llm_provider)
    bundle.quick = CostTrackingLLM(bundle.quick, price=price)
    deep_tracker = CostTrackingLLM(bundle.deep, price=price)
    bundle.deep = deep_tracker if bundle.deep is not bundle.quick else bundle.quick
    trackers = {bundle.quick, bundle.deep}

    # display symbol XAUUSD (venue-tradable); GC=F only inside the loader
    def gold_loader(symbol, curr_date):
        from tradingagents.dataflows.stockstats_utils import load_ohlcv

        return load_ohlcv("GC=F" if symbol == "XAUUSD" else symbol, curr_date)

    builder = build_gold_pipeline(loader=gold_loader)

    def snapshot_source():
        return builder.build("XAUUSD", AssetClass.GOLD, bar_limit=250)

    data_dir = Path(tempfile.mkdtemp(prefix="pro-live-"))
    limits = RiskLimits()
    memory = ProMemory()
    state = DashboardState(memory=memory)
    router = ExecutionRouter(
        adapter=PaperVenueAdapter(VENUES["mt5"], starting_cash=100_000.0),
        limits=limits,
        kill_switch=KillSwitch(),
        breaker=CircuitBreaker(limits, equity_base=100_000.0),
        audit=AuditLog(data_dir / "audit.jsonl"),
    )
    state.router = router
    state.equity = 100_000.0

    service = PaperTradingService(
        bundle, config, snapshot_source,
        router=router, memory=memory, dashboard_state=state,
        alerts=AlertManager(sinks=[LogAlertSink(),
                                   BroadcastAlertSink(state.broadcaster)]),
        on_event=state.broadcaster.publish,
    )

    print("running ONE live pipeline iteration on today's gold tape…")
    summary = service.run_once()
    cost = sum(t.report.est_cost_usd for t in trackers)
    calls = sum(t.report.calls for t in trackers)
    print(f"\ndecision summary: {summary}")
    print(f"LLM calls {calls}, est cost ${cost:.2f}")
    run = state.latest_run()
    if run and run.recommendation:
        rec = run.recommendation
        print(f"verdict: {rec.action.value} conf {rec.confidence} "
              f"entry {rec.entry_price} stop {rec.stop_loss}")
    elif run and run.rejection:
        print(f"verdict: REJECTED at {run.rejection.get('stage')} — "
              f"{run.rejection.get('reasons')}")

    print(f"\naudit: {data_dir}/audit.jsonl · serving on :{port} "
          "(no token — local drill)")
    uvicorn.run(create_app(state), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
