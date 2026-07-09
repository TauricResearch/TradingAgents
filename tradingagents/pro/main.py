"""Production entrypoint: paper-trading loop + dashboard in one process.

    python -m tradingagents.pro.main

Runs the full PaperTradingService loop (real models from env, all safety
rails: kill switch, circuit breaker, hash-chained audit, reconciliation)
in a worker thread while uvicorn serves the dashboard. Without an LLM
API key for the configured provider the loop is skipped and the process
serves the dashboard in monitor mode — stated in the logs, not silent.

Env:
    TRADINGAGENTS_LLM_PROVIDER / _QUICK_THINK_LLM / _DEEP_THINK_LLM
    PRO_LOOP_INTERVAL_SECONDS   (default 3600 — one decision per hour)
    PRO_LOOP_DISABLED=1         dashboard-only regardless of keys
    TRADINGAGENTS_PRO_DATA      audit/prefs dir (volume in Docker)
    PRO_DASHBOARD_TOKEN         dashboard auth
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 3600.0


def loop_enabled() -> bool:
    if os.environ.get("PRO_LOOP_DISABLED") == "1":
        return False
    from tradingagents.llm_clients.api_key_env import get_api_key_env

    provider = os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "deepseek")
    key_env = get_api_key_env(provider)
    return bool(key_env and os.environ.get(key_env))


def build_service(llm=None, data_dir: str | Path | None = None):
    """Assemble the live service + dashboard state. ``llm`` is injectable
    for tests; production builds the env-configured bundle."""
    from tradingagents.contracts import AssetClass, ModelRouting, ProConfig, RiskLimits
    from tradingagents.pro.alerting import AlertManager, LogAlertSink
    from tradingagents.pro.dashboard.app import DashboardState
    from tradingagents.pro.dashboard.events import BroadcastAlertSink
    from tradingagents.pro.dashboard.prefs import PrefsStore, default_data_dir
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
    from tradingagents.pro.service import PaperTradingService

    routing = ModelRouting(
        llm_provider=os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "deepseek"),
        quick_think_llm=os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", "deepseek-chat"),
        deep_think_llm=os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "deepseek-chat"),
    )
    config = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1, models=routing)

    if llm is None:
        from tradingagents.pro.models import bundle_from_config

        llm = bundle_from_config(config, temperature=0.2)

    data_path = Path(data_dir) if data_dir else default_data_dir()
    data_path.mkdir(parents=True, exist_ok=True)

    limits = RiskLimits()
    memory = ProMemory()
    state = DashboardState(memory=memory)
    state.prefs = PrefsStore(data_path / "dashboard_prefs.json")
    router = ExecutionRouter(
        adapter=PaperVenueAdapter(VENUES["mt5"], starting_cash=100_000.0),
        limits=limits,
        kill_switch=KillSwitch(data_path / "KILL"),
        breaker=CircuitBreaker(limits, equity_base=100_000.0),
        audit=AuditLog(data_path / "audit.jsonl"),
    )
    state.router = router
    state.equity = 100_000.0

    builder = build_gold_pipeline()

    def snapshot_source():
        from tradingagents.contracts import AssetClass as AC

        return builder.build("GC=F", AC.GOLD, bar_limit=250)

    service = PaperTradingService(
        llm, config, snapshot_source,
        router=router, memory=memory, dashboard_state=state,
        alerts=AlertManager(sinks=[LogAlertSink(),
                                   BroadcastAlertSink(state.broadcaster)]),
        on_event=state.broadcaster.publish,
    )
    return service, state


def main() -> None:
    import uvicorn

    from tradingagents.pro.dashboard.app import create_app
    from tradingagents.pro.observability import configure_structured_logging

    configure_structured_logging()

    interval = float(os.environ.get("PRO_LOOP_INTERVAL_SECONDS",
                                    DEFAULT_INTERVAL_SECONDS))
    if loop_enabled():
        service, state = build_service()
        logger.info("paper-trading loop enabled: one decision every %.0fs "
                    "(real LLM calls — provider %s)", interval,
                    os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "deepseek"))
        thread = threading.Thread(
            target=service.run_forever,
            kwargs={"interval_seconds": interval},
            name="paper-loop", daemon=True,
        )
        thread.start()
    else:
        from tradingagents.pro.dashboard.app import DashboardState

        state = DashboardState()
        logger.warning(
            "paper-trading loop DISABLED (no LLM key for the configured "
            "provider, or PRO_LOOP_DISABLED=1) — dashboard in monitor mode"
        )

    uvicorn.run(create_app(state), host="0.0.0.0", port=8600,
                log_level="warning")


if __name__ == "__main__":
    main()
