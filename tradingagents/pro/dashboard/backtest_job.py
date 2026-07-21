"""Interactive backtest jobs: run the replay pipeline as a background job
that streams live progress + trades over the dashboard's event broadcaster.

Two engines behind one job: the deterministic scripted pipeline (free, fast,
mechanics-only — the default) and, when ``use_llm`` is set, the real pipeline
built from the operator's ``.env`` keys (costs money, slow, capped). Either
way the job publishes ``backtest_progress`` ticks, one ``backtest_trade`` per
closed trade, and a terminal ``backtest_done`` / ``backtest_error`` — the SPA
already holds one EventSource open, so no new stream endpoint is needed.

Long intraday windows page backward through the 1000-bars/request vendor cap
(``fetch_window``) so "1Y at 1h" really fetches a year.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.contracts import (
    DEFAULT_SYMBOLS,
    OHLCVBar,
    ProConfig,
    Timeframe,
    TradingMode,
)
from tradingagents.pro.backtest import (
    BacktestEngine,
    BarReplay,
    SimBroker,
    monte_carlo_summary,
)
from tradingagents.pro.dashboard import service
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
# keep progress granular but bounded regardless of window size
MAX_DECISIONS = 1500
# real-LLM runs are throttled hard: a full year of hourly LLM decisions would
# be thousands of dollars / many hours. Cap the decision count for cost safety.
MAX_LLM_DECISIONS = 300
_ASSET_BY_SYMBOL = {sym: asset for asset, sym in DEFAULT_SYMBOLS.items()}


class BacktestRunRequest(BaseModel):
    """Interactive-run request body (rejects unknown fields → 422)."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(min_length=1, max_length=8)
    duration: str = Field(default="7D")
    use_llm: bool = False
    initial_equity: float = Field(default=100_000.0, gt=0)
    confirm_cost: bool = False


def bars_for_duration(duration: str, timeframe: Timeframe) -> int:
    """Decision bars implied by a run length at a timeframe, plus warm-up."""
    seconds = DURATION_SECONDS[duration]
    span = max(1, math.ceil(seconds / TIMEFRAME_SECONDS[timeframe]))
    return span + MIN_HISTORY


def estimate_llm_cost(decisions: int) -> dict:
    """Rough envelope from observed runs (~$0.02 and ~30s of wall time per
    decision on deepseek-chat). Approximate — shown only as a warning."""
    return {
        "decisions": decisions,
        "est_cost_usd": round(decisions * 0.02, 2),
        "est_minutes": round(decisions * 0.5),
    }


# --- serialization ----------------------------------------------------------


def open_trade_view(pos: _OpenPosition, mark: float) -> dict:
    sign = 1 if pos.side == "BUY" else -1
    return {
        "id": pos.recommendation.id,
        "symbol": pos.recommendation.symbol,
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
    }


# --- job state --------------------------------------------------------------


@dataclass
class BacktestJob:
    """In-flight job snapshot, mirrored to the endpoint for poll/reconnect."""

    id: str
    params: dict
    status: str = "running"  # running | done | error
    progress: dict = field(default_factory=dict)
    open_trades: list[dict] = field(default_factory=list)
    closed_trades: list[dict] = field(default_factory=list)
    error: str | None = None
    result: dict | None = None
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def snapshot(self) -> dict:
        return {
            "job_id": self.id,
            "params": self.params,
            "status": self.status,
            "progress": self.progress,
            "open_trades": self.open_trades,
            "closed_trades": self.closed_trades,
            "error": self.error,
            "result": self.result,
            "started_at": self.started_at,
        }


# --- paging -----------------------------------------------------------------


def fetch_window(
    marketdata: MarketDataService, symbol: str, timeframe: Timeframe, bars: int
) -> list[OHLCVBar]:
    """Page backward through the per-request cap until ``bars`` bars are
    collected or history is exhausted. Returns oldest→newest, trimmed to the
    most recent ``bars``."""
    collected: list[OHLCVBar] = []
    seen: set[datetime] = set()
    end: datetime | None = None
    while len(collected) < bars:
        page = marketdata.get_bars(symbol, timeframe, limit=MAX_LIMIT, end=end)
        fresh = [b for b in page if b.start not in seen]
        if not fresh:
            break  # history exhausted (or vendor returned only dupes)
        for b in fresh:
            seen.add(b.start)
        collected = fresh + collected
        collected.sort(key=lambda b: b.start)
        if len(page) < MAX_LIMIT:
            break  # vendor gave less than a full page → no older history
        end = collected[0].start
    return collected[-bars:] if len(collected) > bars else collected


# --- streaming engine -------------------------------------------------------


class _StreamingEngine(BacktestEngine):
    """BacktestEngine that emits a throttled progress tick per decision and a
    trade event per close. Zero behavioural change (observe, then delegate)."""

    def __init__(
        self,
        *args,
        on_progress: Callable[[dict], None] | None = None,
        on_trade: Callable[[dict], None] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._on_progress = on_progress
        self._on_trade = on_trade
        self._decision_num = 0
        bars = len(self.replay.bars)
        self._total = max(1, (bars - 1 - self.min_history + self.decide_every - 1)
                          // self.decide_every)
        self._every = max(1, self._total // 200)  # ≤ ~200 progress frames

    def _apply_decision(self, state: dict, i: int):
        outcome = super()._apply_decision(state, i)
        self._decision_num += 1
        if self._on_progress is None:
            return outcome
        if self._decision_num % self._every and self._decision_num != self._total:
            return outcome
        mark = self.replay.bars[i].close
        equity = self.broker.equity(mark_price=mark)
        self._on_progress({
            "decisions": self._decision_num,
            "total": self._total,
            "pct": round(100.0 * self._decision_num / self._total, 1),
            "open_count": self.broker.open_count,
            "closed_trades": len(self.broker.closed),
            "equity": equity,
            "pnl": equity - self.broker.initial_equity,
            "last_time": self.replay.bars[i].start.isoformat(),
            "open_trades": [
                open_trade_view(p, mark) for p in self.broker.positions.values()
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
    a ``_CostConfirmationRequired`` for an unconfirmed LLM run (→ 400)."""
    symbol = params["symbol"]
    if symbol not in _ASSET_BY_SYMBOL:
        raise ValueError(f"unknown symbol {symbol}")
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

    bars = bars_for_duration(duration, tf)
    use_llm = bool(params.get("use_llm"))
    decisions = max(1, bars - MIN_HISTORY)
    if use_llm:
        # hard cost cap: trim to the most-recent MAX_LLM_DECISIONS window
        bars = min(bars, MIN_HISTORY + MAX_LLM_DECISIONS)
        decisions = max(1, bars - MIN_HISTORY)
        if not params.get("confirm_cost"):
            raise _CostConfirmationRequired(estimate_llm_cost(decisions))
    return {
        "symbol": symbol,
        "asset": _ASSET_BY_SYMBOL[symbol],
        "timeframe": tf,
        "duration": duration,
        "bars": bars,
        "use_llm": use_llm,
        "initial_equity": float(params.get("initial_equity", 100_000.0)),
    }


class _CostConfirmationRequired(Exception):
    def __init__(self, estimate: dict):
        self.estimate = estimate
        super().__init__("LLM run requires cost confirmation")


def _build_llm(use_llm: bool, config: ProConfig, cache_dir):
    if not use_llm:
        from tradingagents.pro.evals.scripted import FakePipelineLLM

        return FakePipelineLLM(), (), "deterministic"
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
    the completed run, and always mirrors the latest snapshot onto ``job``."""
    broadcaster = state.broadcaster

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

    try:
        resolved = resolve_request(state.marketdata, params)
        tf: Timeframe = resolved["timeframe"]
        symbol = resolved["symbol"]
        bars = fetch_window(state.marketdata, symbol, tf, resolved["bars"])
        if len(bars) < MIN_HISTORY + 5:
            raise ValueError(
                f"only {len(bars)} bars available; need >= {MIN_HISTORY + 5}")

        # bound total pipeline invocations on large windows (a full year of
        # hourly bars would otherwise be ~8.7k scripted runs)
        decision_bars = max(1, len(bars) - 1 - MIN_HISTORY)
        decide_every = max(1, math.ceil(decision_bars / MAX_DECISIONS))

        config = ProConfig(asset=resolved["asset"], mode=TradingMode.BACKTEST,
                           max_debate_rounds=1, models=_routing(resolved["use_llm"]))
        cache_dir = _cache_dir(symbol, tf)
        llm, trackers, provider = _build_llm(resolved["use_llm"], config, cache_dir)

        from tradingagents.pro.memory import ProMemory

        engine = _StreamingEngine(
            llm, config,
            BarReplay(symbol, resolved["asset"], bars, window=MIN_HISTORY),
            broker=SimBroker(
                initial_equity=resolved["initial_equity"],
                max_open_positions=config.risk.max_open_positions,
                max_gross_exposure_pct=(config.risk.max_open_positions
                                        * config.risk.max_position_pct_equity),
                max_same_direction=config.risk.max_same_direction_positions,
            ),
            memory=ProMemory(),  # isolated — never the live record
            min_history=MIN_HISTORY,
            decide_every=decide_every,
            periods_per_year=_PERIODS_PER_YEAR.get(tf, 365),
            on_progress=on_progress,
            on_trade=on_trade,
        )
        result = engine.run()
        mc = (monte_carlo_summary([t.pnl for t in result.trades],
                                  resolved["initial_equity"])
              if len(result.trades) >= 2 else None)
        state.backtest, state.monte_carlo = result, mc

        view = service.backtest_view(result, mc)
        view.update({
            "provider": provider,
            "symbol": symbol,
            "timeframe": tf.value,
            "duration": resolved["duration"],
            "window": [bars[0].start.date().isoformat(),
                       bars[-1].start.date().isoformat()],
            "trades": [closed_trade_view(t) for t in result.trades],
        })
        if trackers:
            view["est_cost_usd"] = round(sum(t.report.est_cost_usd for t in trackers), 4)
            view["llm_calls"] = sum(t.report.calls for t in trackers)

        record = {
            "id": job.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "params": job.params,
            "view": view,
        }
        if getattr(state, "backtest_runs", None) is not None:
            state.backtest_runs.save(record)

        job.result = view
        job.status = "done"
        publish("backtest_done", {"status": "done", "view": view})
    except _CostConfirmationRequired:
        raise  # resolved before the thread starts; never reached here
    except Exception as exc:  # noqa: BLE001 — surface, never crash the server
        logger.exception("backtest job %s failed", job.id)
        job.status = "error"
        job.error = str(exc)
        publish("backtest_error", {"status": "error", "error": str(exc)})


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


def _cache_dir(symbol: str, tf: Timeframe):
    from tradingagents.pro.dashboard.prefs import default_data_dir

    d = default_data_dir() / "backtest_cache" / f"{symbol}_{tf.value}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_job(params: dict) -> BacktestJob:
    return BacktestJob(id=uuid.uuid4().hex[:12], params=dict(params))


__all__ = [
    "BacktestJob",
    "BacktestRunRequest",
    "DURATION_SECONDS",
    "MAX_LLM_DECISIONS",
    "MIN_HISTORY",
    "bars_for_duration",
    "estimate_llm_cost",
    "fetch_window",
    "new_job",
    "resolve_request",
    "run_job",
    "_CostConfirmationRequired",
]
