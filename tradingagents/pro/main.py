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
    PRO_LOOP_DISABLED=1         skip the automatic hourly loop only — the
                                service still builds and on-demand runs
                                (POST /api/pipeline/run) keep working as
                                long as an LLM key is present
    TRADINGAGENTS_PRO_DATA      audit/prefs dir (volume in Docker)
    PRO_DASHBOARD_TOKEN         dashboard auth
    PORT                        uvicorn bind port (default 8600; Cloud Run
                                injects its own value)
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from tradingagents.contracts import utc_now

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


class _DeltaPerpMetrics:
    """MetricsFeed adapter: Delta funding/OI/mark for a crypto roster."""

    name = "delta_exchange"

    def __init__(self, feed, vendor_symbol: str = "BTCUSD"):
        self._feed = feed
        self._vendor = vendor_symbol

    def get_metrics(self):
        return self._feed.get_metrics(self._vendor)


# crypto universe wiring: dashboard symbol -> (Delta perp, CoinMetrics asset)
CRYPTO_WIRING: dict[str, tuple[str, str]] = {
    "BTC-USD": ("BTCUSD", "btc"),
    "ETH-USD": ("ETHUSD", "eth"),
    "SOL-USD": ("SOLUSD", "sol"),
}


def _crypto_snapshot_builder(symbol: str):
    """One SnapshotBuilder per crypto symbol: Delta bars/derivatives +
    CoinMetrics on-chain + Fear & Greed + Yahoo news — the BTC wiring,
    parameterized (Phase 2 of the score plan: ETH/SOL are config, not code)."""
    from tradingagents.pro.ingestion.builder import SnapshotBuilder
    from tradingagents.pro.ingestion.delta_exchange import DeltaExchangeFeed
    from tradingagents.pro.ingestion.fred_macro import FredMacroFeed
    from tradingagents.pro.ingestion.news import YahooFinanceNewsFeed
    from tradingagents.pro.ingestion.onchain import CoinMetricsFeed, FearGreedFeed
    from tradingagents.pro.ingestion.sessions import current_session

    vendor, cm_asset = CRYPTO_WIRING[symbol]
    delta = DeltaExchangeFeed()
    return SnapshotBuilder(
        bars_feed=_MappedBars(delta, {symbol: vendor}),
        macro_feeds=(FredMacroFeed(),),
        onchain_feeds=(CoinMetricsFeed(asset=cm_asset), FearGreedFeed(),
                       _DeltaPerpMetrics(delta, vendor)),
        news_feed=YahooFinanceNewsFeed(symbol),
        session_fn=current_session,
    )


class TriggerBusy(RuntimeError):
    pass


class PipelineTrigger:
    """On-demand full pipeline run for a chosen pair × timeframe, through
    the SAME service (router, memory, recorder, gates) as the hourly loop.
    One at a time: `busy()` backs the API's 409; the service's run_lock
    additionally serializes against the loop itself."""

    SYMBOLS = ("XAUUSD", "BTC-USD", "ETH-USD", "SOL-USD")
    TIMEFRAMES = ("1h", "4h", "1d")

    def __init__(self, service):
        self.service = service
        self._busy = threading.Lock()
        self.current: dict | None = None  # {"symbol","timeframe"} while running

    def busy(self) -> bool:
        return self._busy.locked()

    def run(self, symbol: str, timeframe: str) -> dict:
        from tradingagents.contracts import (
            DEFAULT_SYMBOLS,
            ProConfig,
            Timeframe,
        )

        if symbol not in self.SYMBOLS:
            raise ValueError(f"symbol must be one of {self.SYMBOLS}")
        if timeframe not in self.TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {self.TIMEFRAMES}")
        if not self._busy.acquire(blocking=False):
            raise TriggerBusy("a pipeline run is already in progress")
        try:
            self.current = {"symbol": symbol, "timeframe": timeframe}
            asset = {sym: a for a, sym in DEFAULT_SYMBOLS.items()}[symbol]
            config = ProConfig(asset=asset, max_debate_rounds=1,
                               models=self.service.config.models)
            tf = Timeframe(timeframe)
            snapshot = self._build_snapshot(symbol, asset, tf)
            return self.service.run_once(snapshot=snapshot, config=config,
                                         trigger="operator")
        finally:
            self.current = None
            self._busy.release()

    def _build_snapshot(self, symbol: str, asset, tf):
        from tradingagents.contracts import Timeframe
        from tradingagents.pro.dashboard.prefs import default_data_dir
        from tradingagents.pro.ingestion.builder import SnapshotBuilder
        from tradingagents.pro.ingestion.delta_exchange import DeltaExchangeFeed
        from tradingagents.pro.ingestion.fred_macro import FredMacroFeed
        from tradingagents.pro.ingestion.gold_feeds import (
            GoldCrossAssetFeed,
            YFinanceDailyBarsFeed,
        )
        from tradingagents.pro.ingestion.positioning import GoldCotFeed, GoldVolFeed
        from tradingagents.pro.ingestion.sessions import current_session

        if symbol == "XAUUSD":
            if tf is Timeframe.D1:
                # the loop's canonical daily gold path (GC=F futures)
                def gold_loader(sym: str, curr_date: str):
                    from tradingagents.dataflows.stockstats_utils import load_ohlcv

                    return load_ohlcv("GC=F" if sym == "XAUUSD" else sym, curr_date)

                from tradingagents.pro.ingestion.builder import build_gold_pipeline

                builder = build_gold_pipeline(
                    loader=gold_loader,
                    cot_cache_path=default_data_dir() / "cot_cache.json",
                )
            else:
                # intraday gold: Delta XAUT (≈ spot) + the same macro context
                delta = DeltaExchangeFeed()
                yf = YFinanceDailyBarsFeed()
                builder = SnapshotBuilder(
                    bars_feed=_MappedBars(delta, {"XAUUSD": "XAUTUSD"}),
                    macro_feeds=(
                        GoldCrossAssetFeed(yf), FredMacroFeed(),
                        GoldCotFeed(cache_path=default_data_dir()
                                    / "cot_cache.json"),
                        GoldVolFeed(yf),
                    ),
                    session_fn=current_session,
                )
        else:
            builder = _crypto_snapshot_builder(symbol)
        return builder.build(symbol, asset, timeframes=(tf,), bar_limit=250)


def _build_alert_sinks(broadcaster, prefs=None):
    """Assemble alert sinks from the environment (go-live Phase 5). Log +
    dashboard broadcast always, plus the bell (NotificationSink) when a
    prefs store exists — the trader review caught the bell reading "All
    clear" through a run start, a completion, and two feed outages because
    nothing ever persisted notifications. Telegram and webhook are added
    only when their secrets are present, so paper/dev stays quiet by
    default."""
    from tradingagents.pro.alerting import (
        LogAlertSink,
        TelegramAlertSink,
        WebhookAlertSink,
    )
    from tradingagents.pro.dashboard.events import BroadcastAlertSink
    from tradingagents.pro.dashboard.prefs import NotificationSink
    from tradingagents.pro.secrets import get_secret

    sinks = [LogAlertSink(), BroadcastAlertSink(broadcaster)]
    if prefs is not None:
        sinks.append(NotificationSink(prefs))
    bot_token = get_secret("PRO_TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("PRO_TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        sinks.append(TelegramAlertSink(bot_token, chat_id))
        logger.info("Telegram alert sink enabled")
    webhook_url = get_secret("PRO_ALERT_WEBHOOK_URL")
    if webhook_url:
        sinks.append(WebhookAlertSink(webhook_url))
        logger.info("webhook alert sink enabled")
    return sinks


def _bell_on_event(state):
    """SSE publish + bell persistence for run outcomes (review P1.4).

    Alerts already reach the bell through NotificationSink; run completions
    are not alerts (they'd spam Telegram), yet a verdict landing while the
    trader was away is exactly what the bell exists to hold."""
    def on_event(type_: str, data: dict) -> None:
        state.broadcaster.publish(type_, data)
        if type_ != "run":
            return
        try:
            action = data.get("action")
            outcome = action or (
                f"rejected @ {data.get('rejected_at')}"
                if data.get("rejected_at") else "no decision"
            )
            state.prefs.add_notification(
                severity="info", event="run_complete",
                text=f"run complete — {data.get('symbol', '?')}: {outcome}",
                time=utc_now().isoformat(),
            )
        except Exception:
            logger.exception("bell notification for run event failed")
    return on_event


def has_llm_key() -> bool:
    """True when an API key exists for the configured provider — independent
    of PRO_LOOP_DISABLED, which only gates the *periodic* background thread
    (on-demand runs still need the service/trigger wired up)."""
    from tradingagents.llm_clients.api_key_env import get_api_key_env

    provider = os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "deepseek")
    key_env = get_api_key_env(provider)
    return bool(key_env and os.environ.get(key_env))


def loop_enabled() -> bool:
    if os.environ.get("PRO_LOOP_DISABLED") == "1":
        return False
    return has_llm_key()


def build_service(llm=None, data_dir: str | Path | None = None):
    """Assemble the live service + dashboard state. ``llm`` is injectable
    for tests; production builds the env-configured bundle."""
    from tradingagents.contracts import AssetClass, ModelRouting, ProConfig, RiskLimits
    from tradingagents.pro.alerting import AlertManager
    from tradingagents.pro.dashboard.app import DashboardState
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
        # opt-in (AI-07): default-on would refuse DeepSeek, which publishes
        # no dated aliases. Live arming (go-live Phase 4) revisits this.
        require_pinned_models=os.environ.get("PRO_REQUIRE_PINNED_MODELS") == "1",
    )
    config = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1, models=routing)

    if llm is None:
        from tradingagents.pro.models import bundle_from_config

        llm = bundle_from_config(config, temperature=0.2)

    data_path = Path(data_dir) if data_dir else default_data_dir()
    data_path.mkdir(parents=True, exist_ok=True)

    from tradingagents.pro.dashboard.recorder import PipelineRecorder

    limits = RiskLimits()
    # persistent memory + venue book: without both, service.rehydrate()
    # has nothing to read after a container restart (go-live Phase 0)
    memory = ProMemory(store_path=data_path / "memory.jsonl")
    state = DashboardState(memory=memory)
    state.recorder = PipelineRecorder(store_dir=data_path / "runs")
    state.prefs = PrefsStore(data_path / "dashboard_prefs.json")
    from tradingagents.pro.dashboard.backtest_firestore import build_run_store
    from tradingagents.pro.dashboard.backtest_job import recover_interrupted
    from tradingagents.pro.dashboard.backtest_store import BacktestRunStore

    state.backtest_runs = build_run_store(data_path)
    state.backtest_optimizations = BacktestRunStore(
        data_path / "backtest_optimizations.json")
    state.backtest_bakeoffs = BacktestRunStore(
        data_path / "backtest_bakeoffs.json")
    try:
        # a leftover running checkpoint = the instance restarted mid-backtest;
        # surface it as a saved partial instead of losing the run
        recover_interrupted(state.backtest_runs)
    except Exception:
        logging.getLogger(__name__).exception("backtest recovery failed")
    router = ExecutionRouter(
        # "paper" venue spans the full tradeable universe; mt5's gold-only
        # map silently venue-rejected every approved BTC order (Phase 2)
        adapter=PaperVenueAdapter(VENUES["paper"], starting_cash=100_000.0,
                                  state_path=data_path / "paper_state.json"),
        limits=limits,
        kill_switch=KillSwitch(data_path / "KILL"),
        breaker=CircuitBreaker(limits, equity_base=100_000.0),
        audit=AuditLog(data_path / "audit.jsonl"),
    )
    state.router = router
    state.equity = router.adapter.account().equity  # reflects a reloaded book

    # per-pair arming state (go-live Phase 4). Every pair defaults to
    # paper; the tradingagents-pro arm-live ceremony flips it, and the
    # dashboard header + /api/flatten read it. Present but paper-only
    # until the live routing lands (Phase 6).
    from tradingagents.pro.arming import ArmingStore

    state.arming = ArmingStore(data_path / "arming.json",
                               audit=router.audit)

    # display symbol is XAUUSD (what the venue trades); GC=F is only the
    # yfinance ticker, mapped inside the loader. First container run
    # proved why: a GC=F-labeled order is refused at venue validation.
    def gold_loader(symbol: str, curr_date: str):
        from tradingagents.dataflows.stockstats_utils import load_ohlcv

        return load_ohlcv("GC=F" if symbol == "XAUUSD" else symbol, curr_date)

    builder = build_gold_pipeline(loader=gold_loader,
                                  cot_cache_path=data_path / "cot_cache.json")

    # multi-symbol rotation (Phase 2): one symbol per hourly tick, so LLM
    # spend stays flat while the whole universe accrues decisions —
    # XAUUSD every 4h, each crypto every 4h. Builders are shared across
    # ticks (feed instances carry caches / respect rate limits).
    import itertools

    from tradingagents.contracts import DEFAULT_SYMBOLS, AssetClass as AC

    crypto_builders = {sym: _crypto_snapshot_builder(sym)
                       for sym in CRYPTO_WIRING}
    asset_by_symbol = {sym: a for a, sym in DEFAULT_SYMBOLS.items()}
    rotation = itertools.cycle(("XAUUSD", "BTC-USD", "ETH-USD", "SOL-USD"))

    def snapshot_source():
        symbol = next(rotation)
        run_config = ProConfig(asset=asset_by_symbol[symbol],
                               max_debate_rounds=1, models=routing)
        if symbol == "XAUUSD":
            return builder.build("XAUUSD", AC.GOLD, bar_limit=250), run_config
        snapshot = crypto_builders[symbol].build(
            symbol, asset_by_symbol[symbol], bar_limit=250)
        return snapshot, run_config

    def next_major_event():
        # fresh countdown per run for the pipeline's event gate (P1.2);
        # IntelService caches under its own TTL so this stays cheap
        return state.intel.calendar(days=7).get("next_major")

    service = PaperTradingService(
        llm, config, snapshot_source,
        router=router, memory=memory, dashboard_state=state,
        alerts=AlertManager(
            sinks=_build_alert_sinks(state.broadcaster, state.prefs)),
        on_event=_bell_on_event(state),
        calendar_fn=next_major_event,
    )
    state.metrics = service.metrics  # /metrics scrape target
    service.alerts.metrics = service.metrics  # count deliveries + failures
    state.alerts = service.alerts    # emergency-flatten alerting
    _wire_staged_routing(state, router, service, data_path)
    return service, state


def _wire_staged_routing(state, router, service, data_path) -> None:
    """Phase 6: the router honors per-pair arming tiers. Shadow tracking
    is always wired (costs nothing until a pair is armed 'shadow'); the
    LIVE route is built only when venue credentials exist — an armed pair
    without a live route is REFUSED by the router, never paper-filled."""
    router.arming = state.arming

    from tradingagents.pro.ingestion.delta_exchange import DeltaExchangeFeed
    from tradingagents.pro.staging import ShadowFillTracker

    vendor_map = {"XAUUSD": "XAUTUSD", "BTC-USD": "BTCUSD"}
    market_data = DeltaExchangeFeed()
    router.shadow_tracker = ShadowFillTracker(
        lambda s: market_data.get_quote(vendor_map.get(s, s)),
        store_path=data_path / "shadow_fills.jsonl",
        metrics=service.metrics,
    )

    testnet = os.environ.get("PRO_LIVE_VENUE", "testnet") != "production"
    try:
        from tradingagents.pro.execution import OrderManager
        from tradingagents.pro.execution.adapters.delta import DeltaAdapter

        live_adapter = DeltaAdapter.from_env(testnet=testnet)
        live_oms = OrderManager(
            live_adapter,
            journal_path=data_path / "oms" / "live_journal.jsonl",
            audit=router.audit,
        )
        live_oms.recover()  # blocking: unresolved live orders = no boot
        router.live_oms = live_oms
        logger.info("live route wired (%s) — orders go live only for "
                    "canary/live-armed pairs",
                    "testnet" if testnet else "PRODUCTION")
    except Exception as exc:
        # no credentials (the common paper case) or venue unreachable:
        # stay paper-only; armed pairs will be refused, honestly
        logger.info("live route not wired (%s) — armed pairs would be "
                    "refused, paper/shadow unaffected", exc)


def _start_live_safety_daemons(service, state) -> None:
    """When any pair is live-armed: warn if on a laptop host, and start the
    dead-man switch (layer c of the kill switch). No-op in paper (go-live
    Phase 5)."""
    import os
    import platform

    arming = getattr(state, "arming", None)
    if arming is None:
        return
    live_armed = any(v["tier"] in ("canary", "live")
                     for v in arming.status().values())
    if not live_armed:
        return

    on_docker_desktop = os.path.exists("/.dockerenv") and (
        "linuxkit" in platform.release().lower())
    if on_docker_desktop or platform.system() == "Darwin":
        msg = ("LIVE-ARMED on a laptop / Docker Desktop host — a sleep "
               "leaves positions unmanaged. Move to an always-on Linux "
               "host with NTP before unattended live trading.")
        logger.warning(msg)
        service.alerts.emit("warning", "armed_on_laptop_host", msg)

    from tradingagents.pro.deadman import DeadManSwitch, cancel_resting_orders
    from tradingagents.pro.health import live_health

    timeout = float(os.environ.get("PRO_DEADMAN_TIMEOUT_SECONDS", "600"))
    deadman = DeadManSwitch(
        health_fn=lambda: live_health(state, state.arming),
        on_trip=cancel_resting_orders(service.router),
        timeout_seconds=timeout, alerts=service.alerts,
    )
    deadman.start()
    state.deadman = deadman
    logger.info("dead-man switch armed (timeout %.0fs)", timeout)


def main() -> None:
    import uvicorn

    from tradingagents.pro.dashboard.app import create_app
    from tradingagents.pro.observability import configure_structured_logging
    from tradingagents.pro.secrets import get_secret

    configure_structured_logging()

    # Phase 3: live mode may never boot with an open dashboard. This
    # entrypoint only ever runs the paper loop (arming live is the Phase-4
    # CLI ceremony), but the guard is here too as defense in depth.
    if os.environ.get("LIVE_TRADING") == "true" and not get_secret(
            "PRO_DASHBOARD_TOKEN"):
        raise SystemExit(
            "refusing to start: LIVE_TRADING=true requires PRO_DASHBOARD_TOKEN "
            "(a control surface over real capital must be authenticated)"
        )

    interval = float(os.environ.get("PRO_LOOP_INTERVAL_SECONDS",
                                    DEFAULT_INTERVAL_SECONDS))
    if has_llm_key():
        service, state = build_service()
        state.trigger = PipelineTrigger(service)
        if loop_enabled():
            logger.info("paper-trading loop enabled: one decision every %.0fs "
                        "(real LLM calls — provider %s)", interval,
                        os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "deepseek"))
            thread = threading.Thread(
                target=service.run_forever,
                kwargs={"interval_seconds": interval},
                name="paper-loop", daemon=True,
            )
            thread.start()
            _start_live_safety_daemons(service, state)
        else:
            logger.warning(
                "automatic paper-trading loop DISABLED (PRO_LOOP_DISABLED=1) "
                "— on-demand pipeline runs remain available"
            )
    else:
        from tradingagents.pro.dashboard.app import DashboardState

        state = DashboardState()
        logger.warning(
            "paper-trading DISABLED (no LLM key for the configured provider) "
            "— dashboard in monitor mode, on-demand runs unavailable"
        )

    port = int(os.environ.get("PORT", 8600))
    uvicorn.run(create_app(state), host="0.0.0.0", port=port,
                log_level="warning")


if __name__ == "__main__":
    main()
