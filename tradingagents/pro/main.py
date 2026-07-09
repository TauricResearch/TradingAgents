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


class _MappedBars:
    """Presents a feed under dashboard symbols (XAUUSD → XAUTUSD, ...)."""

    def __init__(self, feed, mapping: dict[str, str]):
        self._feed = feed
        self._mapping = mapping
        self.name = getattr(feed, "name", "mapped")

    def get_bars(self, symbol, timeframe, *, limit=250, end=None):
        return self._feed.get_bars(self._mapping.get(symbol, symbol),
                                   timeframe, limit=limit, end=end)


class _DeltaBtcMetrics:
    """MetricsFeed adapter: Delta funding/OI/mark for the BTC roster."""

    name = "delta_exchange"

    def __init__(self, feed):
        self._feed = feed

    def get_metrics(self):
        return self._feed.get_metrics("BTCUSD")


class TriggerBusy(RuntimeError):
    pass


class PipelineTrigger:
    """On-demand full pipeline run for a chosen pair × timeframe, through
    the SAME service (router, memory, recorder, gates) as the hourly loop.
    One at a time: `busy()` backs the API's 409; the service's run_lock
    additionally serializes against the loop itself."""

    SYMBOLS = ("XAUUSD", "BTC-USD")
    TIMEFRAMES = ("1h", "4h", "1d")

    def __init__(self, service):
        self.service = service
        self._busy = threading.Lock()
        self.current: dict | None = None  # {"symbol","timeframe"} while running

    def busy(self) -> bool:
        return self._busy.locked()

    def run(self, symbol: str, timeframe: str) -> dict:
        from tradingagents.contracts import AssetClass, ProConfig, Timeframe

        if symbol not in self.SYMBOLS:
            raise ValueError(f"symbol must be one of {self.SYMBOLS}")
        if timeframe not in self.TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {self.TIMEFRAMES}")
        if not self._busy.acquire(blocking=False):
            raise TriggerBusy("a pipeline run is already in progress")
        try:
            self.current = {"symbol": symbol, "timeframe": timeframe}
            asset = AssetClass.GOLD if symbol == "XAUUSD" else AssetClass.BITCOIN
            config = ProConfig(asset=asset, max_debate_rounds=1,
                               models=self.service.config.models)
            tf = Timeframe(timeframe)
            snapshot = self._build_snapshot(symbol, asset, tf)
            return self.service.run_once(snapshot=snapshot, config=config)
        finally:
            self.current = None
            self._busy.release()

    def _build_snapshot(self, symbol: str, asset, tf):
        from tradingagents.contracts import Timeframe
        from tradingagents.pro.ingestion.builder import SnapshotBuilder
        from tradingagents.pro.ingestion.delta_exchange import DeltaExchangeFeed
        from tradingagents.pro.ingestion.fred_macro import FredMacroFeed
        from tradingagents.pro.ingestion.gold_feeds import (
            GoldCrossAssetFeed,
            YFinanceDailyBarsFeed,
        )
        from tradingagents.pro.ingestion.onchain import CoinMetricsFeed, FearGreedFeed
        from tradingagents.pro.ingestion.sessions import current_session

        delta = DeltaExchangeFeed()
        if symbol == "XAUUSD":
            if tf is Timeframe.D1:
                # the loop's canonical daily gold path (GC=F futures)
                def gold_loader(sym: str, curr_date: str):
                    from tradingagents.dataflows.stockstats_utils import load_ohlcv

                    return load_ohlcv("GC=F" if sym == "XAUUSD" else sym, curr_date)

                from tradingagents.pro.ingestion.builder import build_gold_pipeline

                builder = build_gold_pipeline(loader=gold_loader)
            else:
                # intraday gold: Delta XAUT (≈ spot) + the same macro context
                yf = YFinanceDailyBarsFeed()
                builder = SnapshotBuilder(
                    bars_feed=_MappedBars(delta, {"XAUUSD": "XAUTUSD"}),
                    macro_feeds=(GoldCrossAssetFeed(yf), FredMacroFeed()),
                    session_fn=current_session,
                )
        else:
            builder = SnapshotBuilder(
                bars_feed=_MappedBars(delta, {"BTC-USD": "BTCUSD"}),
                macro_feeds=(FredMacroFeed(),),
                onchain_feeds=(CoinMetricsFeed(), FearGreedFeed(),
                               _DeltaBtcMetrics(delta)),
                session_fn=current_session,
            )
        return builder.build(symbol, asset, timeframes=(tf,), bar_limit=250)


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

    from tradingagents.pro.dashboard.recorder import PipelineRecorder

    limits = RiskLimits()
    memory = ProMemory()
    state = DashboardState(memory=memory)
    state.recorder = PipelineRecorder(store_dir=data_path / "runs")
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

    # display symbol is XAUUSD (what the venue trades); GC=F is only the
    # yfinance ticker, mapped inside the loader. First container run
    # proved why: a GC=F-labeled order is refused at venue validation.
    def gold_loader(symbol: str, curr_date: str):
        from tradingagents.dataflows.stockstats_utils import load_ohlcv

        return load_ohlcv("GC=F" if symbol == "XAUUSD" else symbol, curr_date)

    builder = build_gold_pipeline(loader=gold_loader)

    def snapshot_source():
        from tradingagents.contracts import AssetClass as AC

        return builder.build("XAUUSD", AC.GOLD, bar_limit=250)

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
        state.trigger = PipelineTrigger(service)
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
