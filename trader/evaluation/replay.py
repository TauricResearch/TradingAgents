"""Replaying the intraday rules over recorded signals, offline.

The replay drives the real engine (``IntradayPaper``) hour by hour against the
history store, with the signals the live account recorded (or any other series),
so a change of its parameters or a rule laid over the signals can be measured on
the same hours the live account traded, before anything changes live.
"""

from __future__ import annotations

import itertools
import json
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

from trader import report
from trader.evaluation.history import HOUR_MS, MINUTE_MS, HistoryStore
from trader.evaluation.market import HistoricalOKX
from trader.intraday.paper import IntradayPaper
from trader.intraday.settings import DECISION_MINUTE, DEFAULT_PARAMS, Params
from trader.ledger import Fill, Ledger
from trader.okx import OKXError
from trader.settings import WATCHLIST, Coin

DIRECTIONS = ("Long", "Short")


@dataclass(frozen=True)
class Signal:
    ts: int
    coin: str                 # the research key the engine expects, e.g. BTC-USD
    signal: str | None        # Long, Short, Flat, or None when the hour produced none
    conviction: int | None = None


@dataclass(frozen=True)
class Policy:
    """Rules laid over the raw signals before the engine sees them. Everything is off
    by default: the live account follows the signals as they are."""

    # Unit fraction taken at conviction 1, 2 and 3; None sizes every direction alike.
    conviction_weights: tuple[float, float, float] | None = None
    # A reversal (Long after Short or the other way) below this conviction keeps
    # the position instead; 0 follows every reversal.
    flip_min_conviction: int = 0
    # After a stop-out the coin stays flat this many hours; 0 re-enters at once.
    stop_cooldown_hours: int = 0

    def labels(self) -> dict[str, float]:
        """The engine's weights for the labels this policy emits."""
        if self.conviction_weights is None:
            return dict(DEFAULT_PARAMS.weights)
        weights = {"Flat": 0.0}
        for level, w in enumerate(self.conviction_weights, start=1):
            weights[f"Long{level}"] = w
            weights[f"Short{level}"] = -w
        return weights


DEFAULT_POLICY = Policy()


@dataclass
class Result:
    params: Params
    policy: Policy
    capital: float
    equity: list[tuple[int, float]] = field(default_factory=list)  # after each hour
    fills: list[Fill] = field(default_factory=list)
    daily: list[tuple[int, float]] = field(default_factory=list)   # midnight snapshots
    funding: float = 0.0
    exposure: list[float] = field(default_factory=list)            # gross / equity per hour
    halted: bool = False

    @property
    def final_equity(self) -> float:
        return self.equity[-1][1] if self.equity else self.capital

    def metrics(self) -> dict[str, float | int | None]:
        values = [e for _, e in self.equity] or [self.capital]
        daily = [e for _, e in self.daily]
        trades = [f for f in self.fills if f.reason == "trade"]
        stops = [f for f in self.fills if f.reason == "stop"]
        return {
            "return": self.final_equity / self.capital - 1,
            "max_drawdown": report.max_drawdown(values),
            "sharpe": report.sharpe(daily) if len(daily) >= 3 else None,
            "hours": len(self.equity),
            "trades": len(trades),
            "stops": len(stops),
            "kills": sum(1 for f in self.fills if f.reason == "kill"),
            "fees": sum(f.fee for f in self.fills),
            "funding": self.funding,
            "turnover": sum(abs(f.qty * f.price) for f in self.fills),
            "avg_exposure": sum(self.exposure) / len(self.exposure) if self.exposure else 0.0,
            "halted": self.halted,
        }


class _Overlay:
    """Applies a Policy to one hour's raw signals, remembering what it needs between
    hours: the last direction taken per coin and the cooldowns running."""

    def __init__(self, policy: Policy):
        self.policy = policy
        self.last_direction: dict[str, str] = {}
        self.cooldown_until: dict[str, int] = {}

    def apply(self, signals: list[Signal], now_ms: int) -> dict[str, str | None]:
        labels: dict[str, str | None] = {}
        for s in signals:
            labels[s.coin] = self._label(s, now_ms)
        return labels

    def _label(self, s: Signal, now_ms: int) -> str | None:
        p, raw = self.policy, s.signal
        if raw is None:
            return None
        if raw not in DIRECTIONS:
            self.last_direction.pop(s.coin, None)
            return raw
        if now_ms < self.cooldown_until.get(s.coin, 0):
            self.last_direction.pop(s.coin, None)
            return "Flat"
        last = self.last_direction.get(s.coin)
        if p.flip_min_conviction and last and raw != last and (s.conviction or 0) < p.flip_min_conviction:
            return None
        self.last_direction[s.coin] = raw
        if p.conviction_weights is None:
            return raw
        level = min(max(s.conviction or 1, 1), len(p.conviction_weights))
        return f"{raw}{level}"

    def stopped_out(self, coin: str, at_ms: int) -> None:
        if self.policy.stop_cooldown_hours:
            self.cooldown_until[coin] = at_ms + self.policy.stop_cooldown_hours * HOUR_MS
            self.last_direction.pop(coin, None)


def replay(
    store: HistoryStore, signals: list[Signal], start_ms: int, end_ms: int, *,
    params: Params = DEFAULT_PARAMS, policy: Policy = DEFAULT_POLICY,
    watchlist: tuple[Coin, ...] = WATCHLIST, capital: float = 10_000.0,
    ledger_path: Path | None = None,
) -> Result:
    """Run the intraday engine from ``start_ms`` to ``end_ms`` (whole hours, UTC) on
    ``signals``, each hour deciding on the signals recorded in that hour, at the
    minute after the last of them (``DECISION_MINUTE`` when the hour has none).

    The ledger the engine books into is a scratch file (``ledger_path`` to keep it).
    """
    if ledger_path is None:
        ledger_path = Path(tempfile.mkdtemp(prefix="trader-replay-")) / "ledger.sqlite"
    start = start_ms - start_ms % HOUR_MS
    end = end_ms - end_ms % HOUR_MS
    ledger = Ledger(ledger_path)
    # A scratch ledger need not survive a crash: skip the fsync on every statement.
    ledger.db.execute("PRAGMA synchronous=OFF")
    ledger.initialize(capital, start)
    # The baseline is the web's business; the engine would otherwise fetch spot
    # candles for it on its first run. The first snapshot is the engine's too.
    ledger.commit(
        positions={}, cash=capital, snapshots=[(start, capital)],
        meta={"validation_start": start, "baseline_ref": {}},
    )
    market = HistoricalOKX(store, start)
    engine_params = params if policy.conviction_weights is None else replace(params, weights=policy.labels())
    paper = IntradayPaper(ledger, market, watchlist, params=engine_params)
    overlay = _Overlay(policy)
    by_coin = {c.swap: c.research for c in watchlist}
    result = Result(params=params, policy=policy, capital=capital)

    by_hour: dict[int, list[Signal]] = {}
    for s in sorted(signals, key=lambda s: s.ts):
        by_hour.setdefault(s.ts - s.ts % HOUR_MS, []).append(s)

    seen_fills = 0
    for hour in range(start, end, HOUR_MS):
        hourly = by_hour.get(hour, [])
        latest: dict[str, Signal] = {s.coin: s for s in hourly}  # the last one per coin
        now = max((s.ts for s in hourly), default=hour + DECISION_MINUTE * MINUTE_MS)
        now = min(now - now % MINUTE_MS + MINUTE_MS, hour + HOUR_MS - MINUTE_MS)
        market.at(now)
        paper.replay(now)
        for f in ledger.fills()[seen_fills:]:
            if f.reason == "stop" and f.inst in by_coin:
                overlay.stopped_out(by_coin[f.inst], f.ts)
        seen_fills = len(ledger.fills())
        labels = overlay.apply(list(latest.values()), now)
        if labels:
            paper.execute(labels, now)
            seen_fills = len(ledger.fills())
        result.equity.append((now, _mark(paper, market)))
        result.exposure.append(_gross(paper, market) / result.equity[-1][1])
    # The minutes of the last hour: stops, funding and the closing midnight snapshot.
    market.at(end)
    paper.replay(end)
    result.fills = ledger.fills()
    result.daily = ledger.equity_series()
    result.funding = ledger.db.execute("SELECT COALESCE(SUM(amount), 0) FROM funding").fetchone()[0]
    result.halted = bool(ledger.get("halted"))
    return result


def _mark(paper: IntradayPaper, market: HistoricalOKX) -> float:
    prices = {}
    for inst, pos in paper.ledger.positions().items():
        try:
            prices[inst] = market.last_price(inst)
        except OKXError:
            prices[inst] = pos.entry
    return paper.equity(prices)


def _gross(paper: IntradayPaper, market: HistoricalOKX) -> float:
    gross = 0.0
    for inst, pos in paper.ledger.positions().items():
        try:
            gross += abs(pos.qty) * market.last_price(inst)
        except OKXError:
            gross += abs(pos.qty) * pos.entry
    return gross


# -- signal sources -----------------------------------------------------------

def signals_from_ledger(path: Path, start_ms: int = 0, end_ms: int | None = None) -> list[Signal]:
    """The signals an intraday ledger recorded in ``[start_ms, end_ms)``."""
    db = Ledger(path, readonly=True).db
    rows = db.execute(
        "SELECT ts, coin, signal, conviction FROM signals WHERE ts >= ? AND ts < ? ORDER BY ts, id",
        (start_ms, end_ms if end_ms is not None else 1 << 62),
    ).fetchall()
    return [Signal(ts, coin, signal, conviction) for ts, coin, signal, conviction in rows]


def signals_from_json(path: Path) -> list[Signal]:
    """Signals from a JSON list of {ts, coin, signal, conviction} objects."""
    rows = json.loads(path.read_text())
    return [Signal(int(r["ts"]), r["coin"], r.get("signal"), r.get("conviction")) for r in rows]


# -- grids -------------------------------------------------------------------

_PARAM_TYPES = {"risk": float, "stop_mult": float, "atr_bars": int, "rebalance_threshold": float}
_POLICY_TYPES = {"flip_min_conviction": int, "stop_cooldown_hours": int}


def parse_grid(param_specs: list[str], policy_specs: list[str]) -> list[tuple[Params, Policy]]:
    """Every combination of ``name=v1,v2,...`` specs: params by the engine's knobs,
    policies by ``conviction_weights=w1/w2/w3`` (or ``off``), ``flip_min_conviction``
    and ``stop_cooldown_hours``. No specs give the single default pair."""
    axes: list[list[tuple[str, str, object]]] = []
    for spec in param_specs:
        name, values = _split(spec)
        if name not in _PARAM_TYPES:
            raise ValueError(f"unknown param {name!r}; choose from {sorted(_PARAM_TYPES)}")
        axes.append([("param", name, _PARAM_TYPES[name](v)) for v in values])
    for spec in policy_specs:
        name, values = _split(spec)
        if name == "conviction_weights":
            axes.append([("policy", name, _weights(v)) for v in values])
        elif name in _POLICY_TYPES:
            axes.append([("policy", name, _POLICY_TYPES[name](v)) for v in values])
        else:
            raise ValueError(
                f"unknown policy knob {name!r}; choose from"
                f" {sorted([*_POLICY_TYPES, 'conviction_weights'])}"
            )
    pairs = []
    for combo in itertools.product(*axes):
        params, policy = DEFAULT_PARAMS, Policy()
        for kind, name, value in combo:
            if kind == "param":
                params = replace(params, **{name: value})
            else:
                policy = replace(policy, **{name: value})
        pairs.append((params, policy))
    return pairs


def _split(spec: str) -> tuple[str, list[str]]:
    name, _, values = spec.partition("=")
    if not values:
        raise ValueError(f"expected name=value[,value...], got {spec!r}")
    return name.strip(), [v.strip() for v in values.split(",")]


def _weights(text: str) -> tuple[float, float, float] | None:
    if text == "off":
        return None
    parts = [float(p) for p in text.split("/")]
    if len(parts) != 3:
        raise ValueError(f"conviction_weights wants w1/w2/w3, got {text!r}")
    return (parts[0], parts[1], parts[2])


def describe(params: Params, policy: Policy) -> str:
    """One line naming what differs from the live defaults; "默认" when nothing does."""
    parts = []
    for name in _PARAM_TYPES:
        if getattr(params, name) != getattr(DEFAULT_PARAMS, name):
            parts.append(f"{name}={getattr(params, name):g}")
    if policy.conviction_weights is not None:
        parts.append("conviction_weights=" + "/".join(f"{w:g}" for w in policy.conviction_weights))
    for name in _POLICY_TYPES:
        if getattr(policy, name):
            parts.append(f"{name}={getattr(policy, name)}")
    return " ".join(parts) or "默认"


