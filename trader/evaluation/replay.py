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
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from trader import report, rules
from trader.evaluation.history import HOUR_MS, MINUTE_MS, HistoryStore
from trader.evaluation.market import HistoricalOKX
from trader.intraday.paper import IntradayPaper
from trader.intraday.settings import ATR_BAR, DECISION_MINUTE, DEFAULT_PARAMS, Params
from trader.ledger import Fill, Ledger, Position
from trader.okx import OKXError
from trader.settings import WATCHLIST, Coin

DIRECTIONS = ("Long", "Short")

# Makes the hour's signals on the spot: (decision time, the market as of then, the
# positions held) -> signals. A rerun (Issue #28) passes one; a replay of recorded
# signals passes none.
SignalerFn = Callable[[int, "HistoricalOKX", dict[str, Position]], list["Signal"]]


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
    # Favorable move from entry, in hourly ATRs, required before the hourly stop
    # tightens toward the price; 0 tightens every hour.
    trail_after_atr: float = 0.0
    # Hourly efficiency ratio (over er_bars hours) below which directional targets
    # are scaled by er_scale; 0 disables it.
    er_threshold: float = 0.0
    er_scale: float = 0.5
    er_bars: int = 24
    # Consecutive Flat signals required while holding a position before flattening
    # (earlier Flats keep the position); 1 flattens on the first Flat.
    flat_confirm: int = 1

    def __post_init__(self) -> None:
        if self.trail_after_atr < 0:
            raise ValueError(f"trail_after_atr must be >= 0, got {self.trail_after_atr}")
        if not 0.0 <= self.er_threshold <= 1.0:
            raise ValueError(f"er_threshold must be in [0, 1], got {self.er_threshold}")
        if not 0.0 <= self.er_scale <= 1.0:
            raise ValueError(f"er_scale must be in [0, 1], got {self.er_scale}")
        if self.er_bars < 1:
            raise ValueError(f"er_bars must be >= 1, got {self.er_bars}")
        if self.flat_confirm < 1:
            raise ValueError(f"flat_confirm must be >= 1, got {self.flat_confirm}")

    def labels(self) -> dict[str, float]:
        """The engine's weights for the labels this policy emits."""
        if self.conviction_weights is None:
            base = {d: DEFAULT_PARAMS.weights[d] for d in DIRECTIONS}
        else:
            base = {}
            for level, w in enumerate(self.conviction_weights, start=1):
                base[f"Long{level}"] = w
                base[f"Short{level}"] = -w
        weights = {"Flat": 0.0, **base}
        if self.er_threshold > 0 and self.er_scale > 0:
            for label, w in base.items():
                weights[f"{label}_chop"] = w * self.er_scale
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


def efficiency_ratio(market: HistoricalOKX, inst: str, now_ms: int, bars: int = 24) -> float | None:
    """Kaufman efficiency ratio over the last ``bars`` closed hourly changes before
    ``now_ms``: ``|net move| / sum(|hourly moves|)``, in ``[0, 1]``; None when the
    history holds fewer than ``bars + 1`` usable hourly candles."""
    hour = now_ms - now_ms % HOUR_MS
    try:
        hourly = market.bars(inst, ATR_BAR, hour - (bars + 5) * HOUR_MS, hour)
    except OKXError:
        return None
    usable = [b for b in hourly if rules.usable_prices(b.open, b.high, b.low, b.close)]
    if len(usable) < bars + 1:
        return None
    closes = [b.close for b in usable[-(bars + 1):]]
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return 0.0 if path == 0 else abs(closes[-1] - closes[0]) / path


class _Overlay:
    """Applies a Policy to one hour's raw signals, remembering what it needs between
    hours: the last direction taken per coin, the cooldowns running and the consecutive
    Flat count while a position is held."""

    def __init__(self, policy: Policy):
        self.policy = policy
        self.last_direction: dict[str, str] = {}
        self.cooldown_until: dict[str, int] = {}
        self.flat_runs: dict[str, int] = {}

    def apply(
        self, signals: list[Signal], now_ms: int, *,
        market: HistoricalOKX | None = None,
        swap_of: dict[str, str] | None = None,
        positions: dict[str, Position] | None = None,
    ) -> dict[str, str | None]:
        labels: dict[str, str | None] = {}
        for s in signals:
            inst = (swap_of or {}).get(s.coin)
            pos = (positions or {}).get(inst) if inst else None
            held = pos is not None and pos.qty != 0
            labels[s.coin] = self._label(s, now_ms, market, inst, held)
        return labels

    def _label(
        self, s: Signal, now_ms: int, market: HistoricalOKX | None,
        inst: str | None, held: bool,
    ) -> str | None:
        p, raw = self.policy, s.signal
        if raw is None:
            return None
        if raw not in DIRECTIONS:
            if p.flat_confirm > 1 and held:
                self.flat_runs[s.coin] = self.flat_runs.get(s.coin, 0) + 1
                if self.flat_runs[s.coin] < p.flat_confirm:
                    return None
            self.flat_runs.pop(s.coin, None)
            self.last_direction.pop(s.coin, None)
            return raw
        self.flat_runs.pop(s.coin, None)
        if now_ms < self.cooldown_until.get(s.coin, 0):
            self.last_direction.pop(s.coin, None)
            return "Flat"
        last = self.last_direction.get(s.coin)
        if p.flip_min_conviction and last and raw != last and (s.conviction or 0) < p.flip_min_conviction:
            return None
        chop = False
        if p.er_threshold > 0 and market is not None and inst is not None:
            er = efficiency_ratio(market, inst, now_ms, p.er_bars)
            chop = er is not None and er < p.er_threshold
        if chop and p.er_scale == 0.0:
            self.last_direction.pop(s.coin, None)
            return "Flat"
        self.last_direction[s.coin] = raw
        if p.conviction_weights is None:
            base = raw
        else:
            level = min(max(s.conviction or 1, 1), len(p.conviction_weights))
            base = f"{raw}{level}"
        return f"{base}_chop" if chop else base

    def stopped_out(self, coin: str, at_ms: int) -> None:
        self.flat_runs.pop(coin, None)
        if self.policy.stop_cooldown_hours:
            self.cooldown_until[coin] = at_ms + self.policy.stop_cooldown_hours * HOUR_MS
            self.last_direction.pop(coin, None)


def _hold_unearned_stops(
    ledger: Ledger, market: HistoricalOKX, before: dict[str, Position],
    new_fills: list[Fill], now_ms: int, params: Params, trail_after_atr: float,
) -> None:
    """Keep each surviving position's pre-hour stop until its favorable move from entry
    reaches ``trail_after_atr`` hourly ATRs; same-side adds still apply ``stop_after_trade``
    against that pre-hour stop."""
    after = ledger.positions()
    hour = now_ms - now_ms % HOUR_MS
    changed = False
    for inst, old in before.items():
        cur = after.get(inst)
        if cur is None or (cur.qty > 0) != (old.qty > 0):
            continue
        if any(f.inst == inst and f.reason == "stop" for f in new_fills):
            continue
        try:
            hourly = market.bars(inst, ATR_BAR, hour - (params.atr_bars + 5) * HOUR_MS, hour)
            atr_value = rules.atr(
                [b.high for b in hourly], [b.low for b in hourly], [b.close for b in hourly],
                days=params.atr_bars,
            )
            price = market.last_price(inst)
        except (OKXError, ValueError):
            continue
        if not rules.usable_quote(price, atr_value):
            continue
        gain = (price - old.entry) if old.qty > 0 else (old.entry - price)
        if gain >= trail_after_atr * atr_value:
            continue
        trades = [f for f in new_fills if f.inst == inst and f.reason == "trade"]
        if trades and abs(cur.qty) > abs(old.qty):
            wanted = rules.stop_after_trade(
                old.qty, cur.qty, old.stop, trades[-1].price, atr_value,
                stop_mult=params.stop_mult,
            )
        else:
            wanted = old.stop
        if cur.stop != wanted:
            cur.stop = wanted
            changed = True
    if changed:
        ledger.commit(positions=after, cash=ledger.get("cash"))


def replay(
    store: HistoryStore, signals: list[Signal], start_ms: int, end_ms: int, *,
    params: Params = DEFAULT_PARAMS, policy: Policy = DEFAULT_POLICY,
    watchlist: tuple[Coin, ...] = WATCHLIST, capital: float = 10_000.0,
    ledger_path: Path | None = None, signaler: SignalerFn | None = None,
    market: HistoricalOKX | None = None,
) -> Result:
    """Run the intraday engine from ``start_ms`` to ``end_ms`` (whole hours, UTC) on
    ``signals``, each hour deciding on the signals recorded in that hour, at the
    minute after the last of them (``DECISION_MINUTE`` when the hour has none).

    With a ``signaler`` the hour's signals are made at ``DECISION_MINUTE`` instead,
    after the hour's minutes are replayed, seeing the positions held then, as the live
    job does; ``signals`` is then ignored.

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
    market = market if market is not None else HistoricalOKX(store, start)
    market.at(start)
    needs_labels = policy.conviction_weights is not None or policy.er_threshold > 0
    engine_params = replace(params, weights=policy.labels()) if needs_labels else params
    paper = IntradayPaper(ledger, market, watchlist, params=engine_params)
    overlay = _Overlay(policy)
    by_coin = {c.swap: c.research for c in watchlist}
    swap_of = {c.research: c.swap for c in watchlist}
    result = Result(params=params, policy=policy, capital=capital)

    by_hour: dict[int, list[Signal]] = {}
    for s in sorted(signals, key=lambda s: s.ts):
        by_hour.setdefault(s.ts - s.ts % HOUR_MS, []).append(s)

    seen_fills = 0
    for hour in range(start, end, HOUR_MS):
        hourly = [] if signaler is not None else by_hour.get(hour, [])
        if signaler is not None or not hourly:
            now = hour + DECISION_MINUTE * MINUTE_MS
        else:
            now = max(s.ts for s in hourly)
            now = min(now - now % MINUTE_MS + MINUTE_MS, hour + HOUR_MS - MINUTE_MS)
        market.at(now)
        paper.replay(now)
        for f in ledger.fills()[seen_fills:]:
            if f.reason == "stop" and f.inst in by_coin:
                overlay.stopped_out(by_coin[f.inst], f.ts)
        seen_fills = len(ledger.fills())
        positions = ledger.positions()
        if signaler is not None:
            hourly = signaler(now, market, positions)
        latest: dict[str, Signal] = {s.coin: s for s in hourly}  # the last one per coin
        labels = overlay.apply(
            list(latest.values()), now, market=market, swap_of=swap_of, positions=positions,
        )
        if labels:
            paper.execute(labels, now)
            new_fills = ledger.fills()[seen_fills:]
            if policy.trail_after_atr > 0:
                _hold_unearned_stops(
                    ledger, market, positions, new_fills, now, engine_params, policy.trail_after_atr,
                )
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
_POLICY_TYPES = {
    "flip_min_conviction": int,
    "stop_cooldown_hours": int,
    "trail_after_atr": float,
    "er_threshold": float,
    "er_scale": float,
    "er_bars": int,
    "flat_confirm": int,
}


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
        val = getattr(policy, name)
        if val != getattr(DEFAULT_POLICY, name):
            parts.append(f"{name}={val:g}" if isinstance(val, float) else f"{name}={val}")
    return " ".join(parts) or "默认"


