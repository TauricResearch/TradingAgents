"""Interactive backtest jobs: run the replay pipeline as a background job
that streams live progress + trades over the dashboard's event broadcaster.

Two engines behind one job: the deterministic scripted pipeline (free, fast,
mechanics-only — the default) and, when ``use_llm`` is set, the real pipeline
built from the operator's ``.env`` keys (costs money, slow, capped). Either
way the job publishes ``backtest_progress`` ticks, one ``backtest_trade`` per
closed trade, and a slim terminal ``backtest_done`` / ``backtest_error`` —
the SPA already holds one EventSource open, so no new stream endpoint is
needed. Bulk results (full equity curve, all trades, every decision) are
written incrementally as per-run artifacts (``backtest_artifacts``), so a
cancel or an instance restart preserves everything up to the last checkpoint
and NOTHING is downsampled.

Long intraday windows page backward through the 1000-bars/request vendor cap
(``fetch_window``) with retry + live fetch progress, so "1Y at 5m" really
fetches a year and a transient 429 never kills a run.
"""

from __future__ import annotations

import logging
import math
import threading
import time as _time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.contracts import (
    DEFAULT_SYMBOLS,
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
    performance_report,
)
from tradingagents.pro.dashboard import service
from tradingagents.pro.dashboard.backtest_artifacts import (
    RunArtifacts,
    checkpoint_interval,
)
from tradingagents.pro.dashboard.marketdata import (
    MAX_LIMIT,
    TIMEFRAME_SECONDS,
    MarketDataService,
)

if TYPE_CHECKING:
    from tradingagents.pro.backtest.broker import ClosedTrade, _OpenPosition

logger = logging.getLogger(__name__)

# run length (operator-facing) → seconds. Bars are derived per timeframe.
DURATION_SECONDS: dict[str, int] = {
    "1D": 86_400,
    "7D": 7 * 86_400,
    "30D": 30 * 86_400,
    "1Y": 365 * 86_400,
}
_PERIODS_PER_YEAR: dict[Timeframe, int] = {
    Timeframe.M5: 365 * 288,
    Timeframe.M15: 365 * 96,
    Timeframe.M30: 365 * 48,
    Timeframe.H1: 365 * 24,
    Timeframe.H4: 365 * 6,
    Timeframe.D1: 365,
    Timeframe.W1: 52,
}
MIN_HISTORY = 60
# real-LLM runs are throttled hard: a full year of hourly LLM decisions would
# be thousands of dollars / many hours. Cap the decision count for cost safety
# (a WINDOW trim — full decision density inside the window, never subsampled).
MAX_LLM_DECISIONS = 300
# deterministic runs above this many decisions require an explicit confirm
# (same 400-with-estimate flow as the LLM cost gate) — they can take a while
LARGE_RUN_DECISIONS = 20_000
# measured full-pipeline throughput ON CLOUD RUN (1 vCPU: ~8/s; a dev laptop
# does ~100/s) — used only for the operator-facing time estimate, so estimate
# for the slow case and over-deliver elsewhere
_EST_DECISIONS_PER_SECOND = 10
# how many closed trades the poll snapshot carries (full list is in the
# artifact — this bounds a 2s-interval poll payload, it loses nothing)
SNAPSHOT_TRADES = 100
_ASSET_BY_SYMBOL = {sym: asset for asset, sym in DEFAULT_SYMBOLS.items()}
# assets that do NOT trade 24/7: daily bar counts scale by trading days
_MARKET_CLOSURE_ASSETS = {AssetClass.GOLD}
_TRADING_DAYS_PER_YEAR = 252


class BacktestRunRequest(BaseModel):
    """Interactive-run request body (rejects unknown fields → 422)."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(min_length=1, max_length=8)
    duration: str = Field(default="7D")
    use_llm: bool = False
    initial_equity: float = Field(default=100_000.0, gt=0)
    confirm_cost: bool = False
    # per-run sizing (backtest-only overrides; the live paper loop keeps the
    # RiskLimits defaults). Spot-max default: 33%/position × 3 positions
    # ≈ 99% gross — full capital deployable with zero leverage. On tight
    # intraday stops the notional cap is what actually bounds risk, so the
    # cap, not risk_pct, sets realized risk per trade.
    risk_per_trade_pct: float = Field(default=1.0, gt=0, le=5)
    max_position_pct: float = Field(default=33.0, gt=0, le=100)
    # Strategy SDK (track T1). None ⇒ derive from use_llm (back-compat:
    # use_llm True → pipeline_llm, else rules_v1). strategy_params are
    # validated against the strategy's declared ParamSpace (→ 422 on a bad
    # name/value) and recorded for reproducibility.
    strategy_id: str | None = Field(default=None, max_length=32)
    strategy_params: dict = Field(default_factory=dict)


def bars_for_duration(duration: str, timeframe: Timeframe,
                      asset: AssetClass | None = None) -> int:
    """Decision bars implied by a run length at a timeframe, plus warm-up.

    Crypto trades 24/7 so calendar time == market time; market-closure
    assets (gold) scale daily counts by trading days so "1Y" means ~252
    daily bars, not 365 (which would silently span ~1.4 calendar years)."""
    seconds = DURATION_SECONDS[duration]
    span = max(1, math.ceil(seconds / TIMEFRAME_SECONDS[timeframe]))
    if asset in _MARKET_CLOSURE_ASSETS and timeframe is Timeframe.D1:
        span = max(1, math.ceil(span * 5 / 7))
    return span + MIN_HISTORY


def periods_per_year(timeframe: Timeframe, asset: AssetClass | None = None) -> int:
    if asset in _MARKET_CLOSURE_ASSETS and timeframe is Timeframe.D1:
        return _TRADING_DAYS_PER_YEAR
    return _PERIODS_PER_YEAR.get(timeframe, 365)


def estimate_llm_cost(decisions: int) -> dict:
    """Rough envelope from observed runs (~$0.02 and ~30s of wall time per
    decision on deepseek-chat). Approximate — shown only as a warning."""
    return {
        "decisions": decisions,
        "est_cost_usd": round(decisions * 0.02, 2),
        "est_minutes": round(decisions * 0.5),
    }


def estimate_large_run(decisions: int) -> dict:
    """Time envelope for a big full-density deterministic run (free)."""
    return {
        "decisions": decisions,
        "est_cost_usd": 0.0,
        "est_minutes": max(1, round(decisions / _EST_DECISIONS_PER_SECOND / 60)),
    }


# --- serialization ----------------------------------------------------------


def open_trade_view(pos: _OpenPosition, mark: float) -> dict:
    sign = 1 if pos.side == "BUY" else -1
    return {
        "id": pos.recommendation_id,
        "symbol": pos.symbol,
        "side": pos.side,
        "quantity": pos.quantity,
        "entry_price": pos.entry_price,
        "mark_price": mark,
        "stop": pos.stop,
        "unrealized_pnl": sign * (mark - pos.entry_price) * pos.quantity,
        "opened_at": pos.opened_at.isoformat(),
    }


def closed_trade_view(trade: ClosedTrade) -> dict:
    return {
        "id": trade.recommendation_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": trade.quantity,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "pnl": trade.pnl,
        "reason": trade.reason,
        "opened_at": trade.opened_at.isoformat(),
        "closed_at": trade.closed_at.isoformat(),
        "initial_stop": trade.initial_stop,
        "r_multiple": trade.r_multiple,
        "planned_rr": trade.planned_rr,
    }


def summary_from_view(record_id: str, created_at: str, view: dict) -> dict:
    """The compact row the run-list (and Firestore doc) carries."""
    report = view.get("report") or {}
    return {
        "id": record_id,
        "created_at": created_at,
        "symbol": view.get("symbol"),
        "timeframe": view.get("timeframe"),
        "duration": view.get("duration"),
        "provider": view.get("provider"),
        "status": view.get("status", "done"),
        "n_trades": view.get("n_trades"),
        "final_equity": view.get("final_equity"),
        "total_return": report.get("total_return"),
        "win_rate": report.get("win_rate"),
        "window": view.get("window"),
        "bars": view.get("bars"),
        "decisions": view.get("decisions"),
        "indicator_mode": view.get("indicator_mode"),
        "initial_equity": view.get("initial_equity"),
        "risk_per_trade_pct": view.get("risk_per_trade_pct"),
        "max_position_pct": view.get("max_position_pct"),
        "strategy_id": view.get("strategy_id"),
        "est_cost_usd": view.get("est_cost_usd"),
    }


# --- job state --------------------------------------------------------------


@dataclass
class BacktestJob:
    """In-flight job snapshot, mirrored to the endpoint for poll/reconnect."""

    id: str
    params: dict
    status: str = "running"  # running | done | cancelled | error
    progress: dict = field(default_factory=dict)
    open_trades: list[dict] = field(default_factory=list)
    closed_trades: list[dict] = field(default_factory=list)
    error: str | None = None
    result: dict | None = None
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    cancel: threading.Event = field(default_factory=threading.Event)

    def snapshot(self) -> dict:
        return {
            "job_id": self.id,
            "params": self.params,
            "status": self.status,
            "progress": self.progress,
            "open_trades": self.open_trades,
            # bounded poll payload; the artifact holds every trade
            "closed_trades": self.closed_trades[-SNAPSHOT_TRADES:],
            "closed_total": len(self.closed_trades),
            "error": self.error,
            "result": self.result,
            "started_at": self.started_at,
        }


class BacktestCancelled(Exception):
    """Raised inside the engine loop when the operator cancels the run."""


# --- paging -----------------------------------------------------------------


def fetch_window(
    marketdata: MarketDataService,
    symbol: str,
    timeframe: Timeframe,
    bars: int,
    on_page: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
    retries: int = 3,
    backoff: float = 1.5,
) -> tuple[list[OHLCVBar], bool]:
    """Page backward through the per-request cap until ``bars`` bars are
    collected or history is exhausted. Returns (oldest→newest bars trimmed to
    the most recent ``bars``, truncated_by_vendor_failure).

    Each page retries with exponential backoff — one transient 429 must not
    abort a 100-page fetch. If a page fails for good but enough bars are
    already collected, the run proceeds on the shorter (disclosed) window.
    ``on_page(bars_have, bars_needed)`` streams fetch progress to the UI.
    """
    collected: list[OHLCVBar] = []
    seen: set[datetime] = set()
    end: datetime | None = None
    truncated = False
    while len(collected) < bars:
        if cancel is not None and cancel.is_set():
            raise BacktestCancelled()
        page = None
        for attempt in range(retries):
            try:
                page = marketdata.get_bars(symbol, timeframe, limit=MAX_LIMIT,
                                           end=end)
                break
            except Exception as exc:  # vendor hiccup: 429/timeout/5xx
                if attempt == retries - 1:
                    if len(collected) >= MIN_HISTORY + 50:
                        logger.warning(
                            "vendor failed after %d retries with %d bars "
                            "collected — proceeding on a truncated window",
                            retries, len(collected))
                        truncated = True
                        page = []
                    else:
                        raise ValueError(
                            f"bar fetch failed after {retries} retries: {exc}"
                        ) from exc
                else:
                    _time.sleep(backoff * (2 ** attempt))
        if truncated or not page:
            break
        fresh = [b for b in page if b.start not in seen]
        if not fresh:
            break  # history exhausted (or vendor returned only dupes)
        for b in fresh:
            seen.add(b.start)
        collected = fresh + collected
        collected.sort(key=lambda b: b.start)
        if on_page is not None:
            on_page(min(len(collected), bars), bars)
        if len(page) < MAX_LIMIT:
            break  # vendor gave less than a full page → no older history
        end = collected[0].start
    result = collected[-bars:] if len(collected) > bars else collected
    return result, truncated


# --- streaming engine -------------------------------------------------------


class _StreamingEngine(BacktestEngine):
    """BacktestEngine that emits throttled progress ticks, captures the
    full-fidelity run record (per-decision funnel + per-decision equity),
    honors cancellation, and checkpoints artifacts periodically. Zero
    behavioural change to the strategy (observe, then delegate)."""

    def __init__(
        self,
        *args,
        on_progress: Callable[[dict], None] | None = None,
        on_trade: Callable[[dict], None] | None = None,
        on_checkpoint: Callable[[_StreamingEngine], None] | None = None,
        checkpoint_every: int = 0,
        cancel: threading.Event | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._on_progress = on_progress
        self._on_trade = on_trade
        self._on_checkpoint = on_checkpoint
        self._checkpoint_every = checkpoint_every
        self._cancel = cancel
        self._decision_num = 0
        bars = len(self.replay.bars)
        self._total = max(1, (bars - 1 - self.min_history + self.decide_every - 1)
                          // self.decide_every)
        self._every = max(1, self._total // 200)  # ≤ ~200 progress frames
        # full-fidelity capture: one row per decision, nothing sampled
        self.decisions_log: list[dict] = []
        self.equity_rows: list[list] = []  # [iso_time, equity] per decision

    def _apply_decision(self, state: dict, i: int):
        if self._cancel is not None and self._cancel.is_set():
            raise BacktestCancelled()
        # breathe: this CPU-bound loop shares one process (and the GIL) with
        # the request-serving event loop — without an explicit yield each
        # decision, responses slow to a crawl during long runs, requests
        # stack up, and Cloud Run sheds load with 429s (cancel included)
        _time.sleep(0.002)
        outcome = super()._apply_decision(state, i)
        self._decision_num += 1

        bar = self.replay.bars[i]
        equity = self.broker.equity(mark_price=bar.close)
        rejection = state.get("rejection") or {}
        rec = state.get("recommendation")
        regime = state.get("regime")
        self.decisions_log.append({
            "index": i,
            "time": bar.start.isoformat(),
            "outcome": ("executed" if outcome == "executed"
                        else (f"rejected:{rejection.get('stage')}" if rejection
                              else (outcome or "hold"))),
            "action": getattr(getattr(rec, "action", None), "value", None),
            "confidence": getattr(rec, "confidence", None),
            "reasons": "; ".join(rejection.get("reasons", []) or []),
            "regime": getattr(regime, "value", regime),
        })
        self.equity_rows.append([bar.start.isoformat(), equity])

        if (self._on_checkpoint is not None and self._checkpoint_every
                and self._decision_num % self._checkpoint_every == 0):
            self._on_checkpoint(self)

        if self._on_progress is None:
            return outcome
        if self._decision_num % self._every and self._decision_num != self._total:
            return outcome
        self._on_progress({
            "decisions": self._decision_num,
            "total": self._total,
            "pct": round(100.0 * self._decision_num / self._total, 1),
            "open_count": self.broker.open_count,
            "closed_trades": len(self.broker.closed),
            "equity": equity,
            "pnl": equity - self.broker.initial_equity,
            "last_time": bar.start.isoformat(),
            "open_trades": [
                open_trade_view(p, bar.close)
                for p in self.broker.positions.values()
            ],
        })
        return outcome

    def _report_outcome(self, trade) -> None:
        super()._report_outcome(trade)
        if self._on_trade is not None:
            self._on_trade(closed_trade_view(trade))


# --- worker -----------------------------------------------------------------


def resolve_request(marketdata: MarketDataService, params: dict) -> dict:
    """Validate + normalize a run request into concrete engine inputs.

    Raises ValueError (→ 422) for unknown symbol / unsupported timeframe, and
    ``_CostConfirmationRequired`` (→ 400 with an estimate) for an unconfirmed
    LLM run OR an unconfirmed very large deterministic run."""
    symbol = params["symbol"]
    if symbol not in _ASSET_BY_SYMBOL:
        raise ValueError(f"unknown symbol {symbol}")
    asset = _ASSET_BY_SYMBOL[symbol]
    try:
        tf = Timeframe(params["timeframe"])
    except ValueError as exc:
        raise ValueError(f"unknown timeframe {params['timeframe']}") from exc
    supported = marketdata.spec(symbol).timeframes
    if tf not in supported:
        raise ValueError(
            f"{symbol} does not support {tf.value}; "
            f"available: {[t.value for t in supported]}"
        )
    duration = params["duration"]
    if duration not in DURATION_SECONDS:
        raise ValueError(f"unknown duration {duration}")

    # strategy selection (track T1). strategy_id wins over use_llm; when
    # absent, derive it so pre-SDK requests keep working unchanged. Any
    # registered strategy is runnable, plus the job-built pipeline_llm.
    from tradingagents.pro.backtest import is_registered
    from tradingagents.pro.backtest.registry import strategy_param_space
    from tradingagents.pro.backtest.strategies import RULES_V1_PARAMS

    strategy_id = params.get("strategy_id") or (
        "pipeline_llm" if params.get("use_llm") else "rules_v1")
    if strategy_id != "pipeline_llm" and not is_registered(strategy_id):
        raise ValueError(f"unknown strategy {strategy_id}")
    # validate strategy_params against the chosen strategy's declared schema
    # (pipeline_llm shares the rules_v1 knobs); a bad name/value → 422
    space = (RULES_V1_PARAMS if strategy_id == "pipeline_llm"
             else strategy_param_space(strategy_id))
    strategy_params = space.resolve(params.get("strategy_params") or {})
    use_llm = strategy_id == "pipeline_llm"

    bars = bars_for_duration(duration, tf, asset)
    decisions = max(1, bars - MIN_HISTORY)
    if use_llm:
        # hard cost cap: trim to the most-recent MAX_LLM_DECISIONS window
        bars = min(bars, MIN_HISTORY + MAX_LLM_DECISIONS)
        decisions = max(1, bars - MIN_HISTORY)
        if not params.get("confirm_cost"):
            raise _CostConfirmationRequired(estimate_llm_cost(decisions))
    elif decisions > LARGE_RUN_DECISIONS and not params.get("confirm_cost"):
        # full decision density is never subsampled — big windows just take
        # time, so the operator confirms the time estimate first
        raise _CostConfirmationRequired(estimate_large_run(decisions))
    return {
        "symbol": symbol,
        "asset": asset,
        "timeframe": tf,
        "duration": duration,
        "bars": bars,
        "use_llm": use_llm,
        "strategy_id": strategy_id,
        "strategy_params": strategy_params,
        "initial_equity": float(params.get("initial_equity", 100_000.0)),
        "risk_per_trade_pct": float(params.get("risk_per_trade_pct", 1.0)),
        "max_position_pct": float(params.get("max_position_pct", 33.0)),
    }


class _CostConfirmationRequired(Exception):
    def __init__(self, estimate: dict):
        self.estimate = estimate
        super().__init__("run requires confirmation")


def _build_llm(use_llm: bool, config: ProConfig, cache_dir):
    if not use_llm:
        # indicator-driven rules engine (long/short/HOLD), not the canned
        # always-BUY scripted model — same geometry/gates as the LLM path
        from tradingagents.pro.evals.rules import RulesPipelineLLM

        return RulesPipelineLLM(), (), "rules"
    from tradingagents.pro.backtest.llm_cache import CachingLLM
    from tradingagents.pro.models import bundle_from_config
    from tradingagents.pro.observability import CostTrackingLLM, price_for

    bundle = bundle_from_config(config, temperature=0.2)
    price = price_for(config.models.llm_provider)
    quick_ct = CostTrackingLLM(bundle.quick, price=price)
    deep_ct = (quick_ct if bundle.deep is bundle.quick
               else CostTrackingLLM(bundle.deep, price=price))
    bundle.quick = CachingLLM(quick_ct, mode="auto", path=cache_dir / "quick.jsonl")
    bundle.deep = (bundle.quick if deep_ct is quick_ct
                   else CachingLLM(deep_ct, mode="auto", path=cache_dir / "deep.jsonl"))
    return bundle, {quick_ct, deep_ct}, config.models.llm_provider


def run_job(state: Any, job: BacktestJob, params: dict) -> None:
    """Worker body (runs on a daemon thread). Publishes live events, persists
    artifacts incrementally, and always mirrors the latest snapshot onto
    ``job``. Cancels save a labeled partial; nothing is ever discarded."""
    broadcaster = state.broadcaster
    store = getattr(state, "backtest_runs", None)
    artifacts = RunArtifacts(job.id)

    def publish(kind: str, data: dict) -> None:
        data = {"job_id": job.id, **data}
        try:
            broadcaster.publish(kind, data)
        except Exception:  # a stream hiccup must never kill the run
            logger.debug("broadcast %s failed", kind, exc_info=True)

    def on_progress(payload: dict) -> None:
        job.progress = payload
        job.open_trades = payload.get("open_trades", [])
        publish("backtest_progress", payload)

    def on_trade(trade: dict) -> None:
        job.closed_trades.append(trade)
        publish("backtest_trade", trade)

    def on_checkpoint(engine: _StreamingEngine) -> None:
        try:
            artifacts.write(equity=engine.equity_rows,
                            trades=job.closed_trades,
                            decisions=engine.decisions_log,
                            orders=engine.broker.order_log)
            if store is not None:
                store.write_checkpoint({
                    "job_id": job.id,
                    "params": job.params,
                    "status": "running",
                    "progress": job.progress,
                    "closed_total": len(job.closed_trades),
                    "started_at": job.started_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception:  # persistence hiccups must never kill the run
            logger.warning("backtest checkpoint failed", exc_info=True)

    def finalize(view: dict, status: str) -> None:
        """Persist the (complete or partial) run + artifacts, slim events."""
        view["status"] = status
        created_at = datetime.now(timezone.utc).isoformat()
        summary = summary_from_view(job.id, created_at, view)
        record = {
            "id": job.id,
            "created_at": created_at,
            "schema_version": 1,
            "params": job.params,
            "status": status,
            "summary": summary,
            "view": view,
        }
        if store is not None:
            try:
                store.save(record)
                store.clear_checkpoint()
            except Exception:
                logger.exception("failed to persist backtest run %s", job.id)
        job.result = view
        job.status = status
        # slim terminal event: the record + artifacts are fetched on demand
        publish("backtest_done", {"status": status, "summary": summary})

    engine: _StreamingEngine | None = None
    resolved: dict | None = None
    try:
        resolved = resolve_request(state.marketdata, params)
        tf: Timeframe = resolved["timeframe"]
        symbol = resolved["symbol"]

        def on_page(have: int, need: int) -> None:
            payload = {"phase": "fetching", "bars_have": have,
                       "bars_needed": need,
                       "pct": round(100.0 * have / max(1, need), 1)}
            job.progress = payload
            publish("backtest_progress", payload)

        bars, window_truncated = fetch_window(
            state.marketdata, symbol, tf, resolved["bars"],
            on_page=on_page, cancel=job.cancel)
        if len(bars) < MIN_HISTORY + 5:
            raise ValueError(
                f"only {len(bars)} bars available; need >= {MIN_HISTORY + 5}")

        # per-run sizing overrides; every other RiskLimits knob (ladder,
        # gates, cooldown) keeps its contract default
        risk = RiskLimits(
            max_risk_per_trade_pct=resolved["risk_per_trade_pct"],
            max_position_pct_equity=resolved["max_position_pct"],
        )
        config = ProConfig(asset=resolved["asset"], mode=TradingMode.BACKTEST,
                           max_debate_rounds=1, risk=risk,
                           models=_routing(resolved["use_llm"]))
        cache_dir = _cache_dir(symbol, tf)
        # build the strategy (track T1). rules_v1 is self-contained; pipeline_llm
        # wraps the cost-tracked/cached operator bundle (built here — it's
        # environment, not a tunable). strategy.bind() applies strategy_params
        # to config and builds the pipeline; the engine adopts that config.
        from tradingagents.pro.backtest import PipelineStrategy, build_strategy
        from tradingagents.pro.backtest.strategies import apply_rules_v1_params

        if resolved["strategy_id"] == "pipeline_llm":
            bundle, trackers, provider = _build_llm(True, config, cache_dir)
            strategy = PipelineStrategy(
                "pipeline_llm", resolved["strategy_params"],
                llm_factory=lambda: bundle, config_patch=apply_rules_v1_params)
        else:
            # any registered strategy (rules_v1 pipeline adapter, or a native
            # order-book strategy like trend_following_v1) — all deterministic
            trackers, provider = (), "rules"
            strategy = build_strategy(
                resolved["strategy_id"], resolved["strategy_params"])

        from tradingagents.pro.memory import ProMemory

        # full decision density: every bar gets a decision (no subsampling);
        # precomputed indicator series make that tractable (profiled ~8x)
        replay = BarReplay(symbol, resolved["asset"], bars, window=MIN_HISTORY,
                           precompute_indicators=True)
        total_decisions = max(1, len(bars) - 1 - MIN_HISTORY)
        engine = _StreamingEngine(
            None, config,
            replay,
            strategy=strategy,
            broker=SimBroker(
                initial_equity=resolved["initial_equity"],
                max_open_positions=config.risk.max_open_positions,
                max_gross_exposure_pct=(config.risk.max_open_positions
                                        * config.risk.max_position_pct_equity),
                max_same_direction=config.risk.max_same_direction_positions,
            ),
            memory=ProMemory(),  # isolated — never the live record
            min_history=MIN_HISTORY,
            decide_every=1,
            periods_per_year=periods_per_year(tf, resolved["asset"]),
            on_progress=on_progress,
            on_trade=on_trade,
            on_checkpoint=on_checkpoint,
            checkpoint_every=checkpoint_interval(total_decisions,
                                                 resolved["use_llm"]),
            cancel=job.cancel,
        )

        def build_view(result, partial: bool) -> dict:
            mc = (monte_carlo_summary([t.pnl for t in result.trades],
                                      resolved["initial_equity"])
                  if len(result.trades) >= 2 else None)
            if not partial:
                state.backtest, state.monte_carlo = result, mc
            view = service.backtest_view(result, mc)
            # bulk arrays live in the artifacts, not the record/event
            view.pop("equity_curve", None)
            view.update({
                "provider": provider,
                "symbol": symbol,
                "timeframe": tf.value,
                "duration": resolved["duration"],
                "window": [bars[0].start.date().isoformat(),
                           bars[-1].start.date().isoformat()],
                "window_truncated": window_truncated,
                # reproducibility: exactly what ran
                "bars": len(bars),
                "indicator_mode": replay.indicator_mode,
                "initial_equity": resolved["initial_equity"],
                "risk_per_trade_pct": resolved["risk_per_trade_pct"],
                "max_position_pct": resolved["max_position_pct"],
                "strategy_id": resolved["strategy_id"],
                "strategy_params": resolved["strategy_params"],
                "schema_version": 1,
                "artifacts": (["equity", "trades", "decisions", "orders"]
                              if engine.broker.order_log
                              else ["equity", "trades", "decisions"]),
            })
            if trackers:
                view["est_cost_usd"] = round(
                    sum(t.report.est_cost_usd for t in trackers), 4)
                view["llm_calls"] = sum(t.report.calls for t in trackers)
            return view

        try:
            result = engine.run()
        except BacktestCancelled:
            # partial, honestly labeled: metrics over what completed
            equity_values = ([resolved["initial_equity"]]
                             + [row[1] for row in engine.equity_rows])
            report = performance_report(
                equity_values, engine.broker.closed,
                periods_per_year(tf, resolved["asset"]))
            from tradingagents.pro.backtest.engine import BacktestResult

            executed = sum(1 for d in engine.decisions_log
                           if d["outcome"] == "executed")
            partial = BacktestResult(
                equity_curve=equity_values,
                trades=list(engine.broker.closed),
                report=report,
                decisions=len(engine.decisions_log),
                executed=executed,
            )
            on_checkpoint(engine)  # final artifact flush of the partial
            finalize(build_view(partial, partial=True), "cancelled")
            return

        # final artifact flush with the complete record (incl. end-of-data
        # closes that happen after the last decision)
        job.closed_trades = [closed_trade_view(t) for t in result.trades]
        artifacts.write(
            equity=engine.equity_rows,
            trades=job.closed_trades,
            decisions=engine.decisions_log,
            orders=engine.broker.order_log,
        )
        finalize(build_view(result, partial=False), "done")
    except BacktestCancelled:
        # cancelled during the fetch phase: nothing ran yet
        job.status = "cancelled"
        job.error = None
        if store is not None:
            store.clear_checkpoint()
        publish("backtest_done", {"status": "cancelled", "summary": None})
    except _CostConfirmationRequired:
        raise  # resolved before the thread starts; never reached here
    except Exception as exc:  # noqa: BLE001 — surface, never crash the server
        logger.exception("backtest job %s failed", job.id)
        job.status = "error"
        job.error = str(exc)
        if store is not None:
            try:
                store.clear_checkpoint()
            except Exception:
                logger.debug("checkpoint clear failed", exc_info=True)
        publish("backtest_error", {"status": "error", "error": str(exc)})


def recover_interrupted(store, artifacts_base=None) -> dict | None:
    """Convert a leftover 'running' checkpoint (instance restarted mid-run)
    into a saved run labeled ``interrupted`` — the incrementally-written
    artifacts carry everything up to the last checkpoint, so an interrupted
    run keeps its trades/equity/decisions instead of vanishing."""
    if store is None:
        return None
    checkpoint = store.read_checkpoint()
    if not checkpoint or checkpoint.get("status") != "running":
        return None
    run_id = checkpoint.get("job_id") or uuid.uuid4().hex[:12]
    artifacts = RunArtifacts(run_id, artifacts_base)
    equity = artifacts.read("equity")
    trades = artifacts.read("trades")
    decisions = artifacts.read("decisions")
    params = checkpoint.get("params") or {}
    initial_equity = float(params.get("initial_equity", 100_000.0))
    final_equity = equity[-1][1] if equity else initial_equity
    pnls = [t.get("pnl") for t in trades if t.get("pnl") is not None]
    wins = sum(1 for p in pnls if p > 0)
    created_at = datetime.now(timezone.utc).isoformat()
    view = {
        "status": "interrupted",
        "provider": "deterministic" if not params.get("use_llm") else "llm",
        "symbol": params.get("symbol"),
        "timeframe": params.get("timeframe"),
        "duration": params.get("duration"),
        "initial_equity": initial_equity,
        "final_equity": final_equity,
        "n_trades": len(trades),
        "decisions": len(decisions),
        "strategy_id": params.get("strategy_id"),
        "schema_version": 1,
        "report": {
            "total_return": (final_equity - initial_equity) / initial_equity
            if initial_equity else 0.0,
            "win_rate": (wins / len(pnls)) if pnls else 0.0,
        },
        "window": ([equity[0][0][:10], equity[-1][0][:10]] if equity else None),
        "artifacts": ["equity", "trades", "decisions"],
    }
    record = {
        "id": run_id,
        "created_at": created_at,
        "schema_version": 1,
        "params": params,
        "status": "interrupted",
        "summary": summary_from_view(run_id, created_at, view),
        "view": view,
    }
    try:
        store.save(record)
    finally:
        store.clear_checkpoint()
    logger.warning("recovered interrupted backtest %s (%d decisions, %d trades)",
                   run_id, len(decisions), len(trades))
    return record


# --- optimization jobs (roadmap P2.5/P2.6 / track T3) ------------------------

# a grid this size or larger requires an explicit confirm (each trial is a full
# backtest — same time-estimate gate as a large deterministic run)
OPT_TRIALS_CONFIRM = 50
# cap optimization worker processes: each holds the window's bars +
# precomputed indicator series, so unbounded fan-out on a big grid thrashes
# RAM. min(cpu_count, n_trials, this) picks the effective pool size.
OPT_MAX_WORKERS = 4


class OptimizeRequest(BaseModel):
    """Parameter-optimization request (rejects unknown fields → 422). A grid
    search: ``param_grid`` maps a swept parameter name to the explicit values
    to try; parameters left out keep the strategy's defaults."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(min_length=1, max_length=8)
    duration: str = Field(default="1Y")
    strategy_id: str = Field(default="trend_following_v1", max_length=32)
    param_grid: dict[str, list] = Field(default_factory=dict)
    objective: str = Field(default="sharpe", max_length=32)
    initial_equity: float = Field(default=100_000.0, gt=0)
    confirm_cost: bool = False


def _opt_estimate(n_trials: int, decisions: int) -> dict:
    """Time envelope for a grid: n_trials full backtests, serial."""
    return {
        "trials": n_trials,
        "est_cost_usd": 0.0,
        "est_minutes": max(1, round(
            n_trials * decisions / _EST_DECISIONS_PER_SECOND / 60)),
    }


def resolve_optimize_request(marketdata: MarketDataService, params: dict) -> dict:
    """Validate + normalize an optimization request. Raises ValueError (→422)
    for unknown symbol/timeframe/duration/strategy or a param outside the
    strategy's declared domain, and ``_CostConfirmationRequired`` (→400) for a
    large unconfirmed grid."""
    from tradingagents.pro.backtest import is_registered, objective_choices
    from tradingagents.pro.backtest.registry import strategy_param_space

    symbol = params["symbol"]
    if symbol not in _ASSET_BY_SYMBOL:
        raise ValueError(f"unknown symbol {symbol}")
    asset = _ASSET_BY_SYMBOL[symbol]
    try:
        tf = Timeframe(params["timeframe"])
    except ValueError as exc:
        raise ValueError(f"unknown timeframe {params['timeframe']}") from exc
    if tf not in marketdata.spec(symbol).timeframes:
        raise ValueError(f"{symbol} does not support {tf.value}")
    duration = params["duration"]
    if duration not in DURATION_SECONDS:
        raise ValueError(f"unknown duration {duration}")

    strategy_id = params["strategy_id"]
    if not is_registered(strategy_id):
        raise ValueError(f"strategy {strategy_id} is not optimizable")
    space = strategy_param_space(strategy_id)
    grid = params.get("param_grid") or {}
    if not grid:
        raise ValueError("param_grid must sweep at least one parameter")
    n_trials = 1
    for name, values in grid.items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"param_grid[{name}] must be a non-empty list")
        for v in values:  # each candidate must be in the strategy's domain
            space.resolve({name: v})
        n_trials *= len(values)
    objective = params.get("objective", "sharpe")
    if objective not in objective_choices():
        raise ValueError(
            f"unknown objective {objective}; choices: {list(objective_choices())}")

    bars = bars_for_duration(duration, tf, asset)
    decisions = max(1, bars - MIN_HISTORY)
    if n_trials >= OPT_TRIALS_CONFIRM and not params.get("confirm_cost"):
        raise _CostConfirmationRequired(_opt_estimate(n_trials, decisions))
    return {
        "symbol": symbol, "asset": asset, "timeframe": tf, "duration": duration,
        "bars": bars, "strategy_id": strategy_id, "param_grid": grid,
        "objective": objective, "n_trials": n_trials,
        "initial_equity": float(params.get("initial_equity", 100_000.0)),
    }


def run_optimization_job(state: Any, job: BacktestJob, params: dict) -> None:
    """Worker body (daemon thread): fetch the window once, grid-search the
    strategy's params (each trial a child backtest on the same bars), attach
    the overfitting guards, persist the result, and emit slim SSE events."""
    import os

    from tradingagents.pro.backtest import (
        EngineTrial,
        Param,
        ParamSpace,
        run_optimization,
    )

    broadcaster = state.broadcaster
    store = getattr(state, "backtest_optimizations", None)

    def publish(kind: str, data: dict) -> None:
        try:
            broadcaster.publish(kind, {"job_id": job.id, **data})
        except Exception:
            logger.debug("broadcast %s failed", kind, exc_info=True)

    try:
        resolved = resolve_optimize_request(state.marketdata, params)
        tf: Timeframe = resolved["timeframe"]
        symbol = resolved["symbol"]

        def on_page(have: int, need: int) -> None:
            job.progress = {"phase": "fetching", "bars_have": have,
                            "bars_needed": need,
                            "pct": round(100.0 * have / max(1, need), 1)}
            publish("optimization_progress", job.progress)

        bars, truncated = fetch_window(state.marketdata, symbol, tf,
                                       resolved["bars"], on_page=on_page,
                                       cancel=job.cancel)
        if len(bars) < MIN_HISTORY + 5:
            raise ValueError(f"only {len(bars)} bars available")

        config = ProConfig(asset=resolved["asset"], mode=TradingMode.BACKTEST,
                           max_debate_rounds=1)
        space = ParamSpace(*[
            Param(name, "categorical", choices=tuple(values), default=values[0])
            for name, values in resolved["param_grid"].items()
        ])
        # EngineTrial (not the engine_backtest_fn closure) so the work ships
        # to worker processes — the trial is a pure function of its params
        fn = EngineTrial(
            strategy_id=resolved["strategy_id"], config=config,
            symbol=symbol, asset=resolved["asset"], bars=bars,
            min_history=MIN_HISTORY,
            periods_per_year=periods_per_year(tf, resolved["asset"]),
            initial_equity=resolved["initial_equity"],
            objective_name=resolved["objective"])

        def on_trial(done: int, total: int, best: float) -> None:
            job.progress = {"phase": "optimizing", "trials_done": done,
                            "n_trials": total,
                            "pct": round(100.0 * done / max(1, total), 1),
                            "best_objective": best}
            publish("optimization_progress", job.progress)

        # roadmap R1: trials are embarrassingly parallel — fan them across
        # cores when the box has them (1-vCPU prod resolves to 1 = serial).
        # Capped so a big grid can't spawn a worker per trial and thrash RAM.
        workers = min(os.cpu_count() or 1, resolved["n_trials"], OPT_MAX_WORKERS)
        result = run_optimization(
            space, fn, search="grid", objective_name=resolved["objective"],
            on_trial=on_trial, cancel=job.cancel.is_set, max_workers=workers)

        created_at = datetime.now(timezone.utc).isoformat()
        cancelled = job.cancel.is_set()
        status = "cancelled" if cancelled else "done"
        summary = {
            "id": job.id, "created_at": created_at, "type": "optimization",
            "symbol": symbol, "timeframe": tf.value, "duration": resolved["duration"],
            "strategy_id": resolved["strategy_id"], "objective": resolved["objective"],
            "n_trials": result.n_trials, "status": status,
            "best_objective": result.best_objective,
            "deflated_sharpe": result.deflated_sharpe, "pbo": result.pbo,
        }
        record = {
            "id": job.id, "created_at": created_at, "schema_version": 1,
            "type": "optimization", "params": job.params, "status": status,
            "summary": summary,
            "view": {
                "strategy_id": resolved["strategy_id"], "symbol": symbol,
                "timeframe": tf.value, "duration": resolved["duration"],
                "objective": resolved["objective"], "n_trials": result.n_trials,
                "param_grid": resolved["param_grid"],
                "best_params": result.best_params,
                "best_objective": result.best_objective,
                "deflated_sharpe": result.deflated_sharpe, "pbo": result.pbo,
                "verdict": result.verdict(), "guard_note": result.guard_note,
                "window": [bars[0].start.date().isoformat(),
                           bars[-1].start.date().isoformat()],
                "window_truncated": truncated,
                "trials": [{"params": t.params, "objective": t.objective}
                           for t in result.trials],
            },
        }
        if store is not None:
            try:
                store.save(record)
            except Exception:
                logger.exception("failed to persist optimization %s", job.id)
        job.result = record
        job.status = status
        publish("optimization_done", {"status": status, "summary": summary})
    except _CostConfirmationRequired:
        raise  # resolved before the thread starts; never reached here
    except Exception as exc:  # noqa: BLE001 — surface, never crash the server
        logger.exception("optimization job %s failed", job.id)
        job.status = "error"
        job.error = str(exc)
        publish("optimization_error", {"status": "error", "error": str(exc)})


def _routing(use_llm: bool):
    from tradingagents.contracts import ModelRouting

    if not use_llm:
        return ModelRouting()
    import os

    return ModelRouting(
        llm_provider=os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "openai"),
        quick_think_llm=os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-5.4-mini"),
        deep_think_llm=os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "gpt-5.5"),
    )


# LLM record/replay caches are an optimization, never data — wipe a
# per-symbol dir when it outgrows this budget
_CACHE_DIR_MAX_BYTES = 50 * 1024 * 1024


def _cache_dir(symbol: str, tf: Timeframe):
    from tradingagents.pro.dashboard.prefs import default_data_dir

    d = default_data_dir() / "backtest_cache" / f"{symbol}_{tf.value}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        size = sum(p.stat().st_size for p in d.glob("*.jsonl"))
        if size > _CACHE_DIR_MAX_BYTES:
            logger.info("pruning oversized LLM cache dir %s (%d bytes)", d, size)
            for p in d.glob("*.jsonl"):
                p.unlink(missing_ok=True)
    except OSError:
        logger.debug("cache prune failed", exc_info=True)
    return d


def new_job(params: dict) -> BacktestJob:
    return BacktestJob(id=uuid.uuid4().hex[:12], params=dict(params))


__all__ = [
    "BacktestCancelled",
    "BacktestJob",
    "BacktestRunRequest",
    "OptimizeRequest",
    "OPT_TRIALS_CONFIRM",
    "resolve_optimize_request",
    "run_optimization_job",
    "DURATION_SECONDS",
    "LARGE_RUN_DECISIONS",
    "MAX_LLM_DECISIONS",
    "MIN_HISTORY",
    "SNAPSHOT_TRADES",
    "bars_for_duration",
    "estimate_llm_cost",
    "estimate_large_run",
    "fetch_window",
    "new_job",
    "periods_per_year",
    "recover_interrupted",
    "resolve_request",
    "run_job",
    "summary_from_view",
    "_CostConfirmationRequired",
]
